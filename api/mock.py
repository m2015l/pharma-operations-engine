"""Backend do MODO_DEMO: responde com fixtures gravadas, sem LLM, sem banco.

As fixtures (`fixtures/demo.json`) vêm do acervo real e dos turnos auditados —
ver o campo `_leia_me` do JSON e o `origem` de cada cenário. Nada aqui é gerado
na hora: a pergunta só escolhe QUAL resposta gravada devolver.

A escolha imita o que o agente real faz com o histórico (I8, PRECISÃO.md):
uma pergunta com pronome solto ("e o valor disso?") herda o documento do turno
anterior. Pergunta sem cenário gravado recebe uma resposta explícita de que o
modo demo não tem aquela resposta — nunca uma resposta inventada.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from schemas import CitacaoOut, DocumentoOut, RespostaOut, Turno

FIXTURES = Path(__file__).with_name("fixtures") / "demo.json"

# Palavras que identificam cada documento do acervo (texto normalizado).
_ASSUNTOS = {
    "biopharma": ("biopharma", "instituto biopharma", "isi "),
    "farmaceutico": ("farmaceutico", "vapor puro"),
    "biotecnologia": ("biotecnologia", "bioterio"),
    "imunobiologicos": ("imunobiologicos", "instituto", "criogenia"),
}


def _norm(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " " + re.sub(r"\s+", " ", sem_acento.lower()) + " "


def _tem(texto: str, *padroes: str) -> bool:
    return any(re.search(p, texto) for p in padroes)


@lru_cache(maxsize=1)
def _dados() -> dict:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def _cenario(cid: str) -> dict:
    return next(c for c in _dados()["cenarios"] if c["id"] == cid)


def _assunto_em(texto: str) -> str | None:
    """Primeiro documento mencionado no texto (pela posição da menção)."""
    achados = []
    for chave, termos in _ASSUNTOS.items():
        posicoes = [texto.find(t) for t in termos if t in texto]
        if posicoes:
            achados.append((min(posicoes), chave))
    return min(achados)[1] if achados else None


def _assunto(pergunta: str, historico: list[Turno]) -> str | None:
    """Documento de que a conversa trata: a pergunta vence; senão, o último turno."""
    if (a := _assunto_em(pergunta)) is not None:
        return a
    for turno in reversed(historico):
        a = _assunto_em(_norm(turno.pergunta)) or _assunto_em(_norm(turno.resposta))
        if a is not None:
            return a
    return None


def escolher_cenario(pergunta: str, historico: list[Turno]) -> str | None:
    p = _norm(pergunta)
    assunto = _assunto(p, historico)

    if _tem(p, r"\brodovi", r"\bder\b", r"\bdnit\b"):
        return "rodoviaria"
    if _tem(p, r"hospita", r"gases medicinais"):
        return "hospitalar"
    if _tem(p, r"governo do estado", r"\b2021\b"):
        return "nao_indexado"
    # Atributo de um documento já em pauta ("e o valor disso?") vem antes do
    # assunto: é o caso em que o histórico decide a resposta.
    atributos = (
        ((r"responsavel", r"assinou"), {"biotecnologia": "responsavel_biotecnologia", "biopharma": "responsavel_biopharma"}),
        ((r"\bvalor", r"quanto custou", r"\bpreco"), {"farmaceutico": "valor_farmaceutico", "biopharma": "valor_biopharma"}),
        ((r"\barea", r"\bm2\b", r"metragem"), {"biopharma": "area_biopharma"}),
        ((r"\bprazo", r"aditivo"), {"biopharma": "prazo_biopharma"}),
        ((r"escopo", r"detalh"), {"biotecnologia": "escopo_biotecnologia"}),
    )
    for padroes, por_assunto in atributos:
        if _tem(p, *padroes) and assunto in por_assunto:
            return por_assunto[assunto]

    if _tem(p, r"vapor", r"agua purificada"):
        return "vapor_puro"
    if _tem(p, r"farmac", r"biotec"):
        return "farmaceuticas"
    if _tem(p, r"laborat") and _tem(p, r"obra", r"implant", r"fe[zi]", r"fizemos", r"experiencia"):
        return "laboratorio"
    return None


def _titulos() -> dict[str, str]:
    return {d["id"]: d["titulo"] for d in _dados()["documentos"]}


def responder(pergunta: str, historico: list[Turno]) -> RespostaOut:
    cid = escolher_cenario(pergunta, historico)
    if cid is None:
        sugestoes = "\n".join(
            f"- {c['pergunta_exemplo']}" for c in _dados()["cenarios"] if c["id"] in _SUGERIDOS
        )
        return RespostaOut(
            texto=(
                "Esta é a versão de demonstração: ela só tem as respostas gravadas nas "
                "auditorias do agente, e nenhuma cobre essa pergunta. Nada foi consultado "
                "no acervo.\n\nPerguntas com resposta gravada:\n" + sugestoes
            ),
            citacoes=[],
            trechos_recuperados=0,
            contrato_citacao_ok=True,
            encontrou_no_acervo=False,
            tipo_fluxo="consulta_historico",
            modo="demo",
            origem="sem cenário gravado",
        )

    c = _cenario(cid)
    titulos = _titulos()
    citacoes = [
        CitacaoOut(**cit, titulo_documento=titulos.get(cit["documento_id"], cit["orgao"]))
        for cit in c["citacoes"]
    ]
    return RespostaOut(
        texto=c["texto"],
        citacoes=citacoes,
        trechos_recuperados=c["trechos_recuperados"],
        contrato_citacao_ok=bool(citacoes) or not c["encontrou_no_acervo"],
        encontrou_no_acervo=c["encontrou_no_acervo"],
        tipo_fluxo="consulta_historico",
        modo="demo",
        origem=c["origem"],
    )


_SUGERIDOS = {"laboratorio", "vapor_puro", "farmaceuticas", "escopo_biotecnologia", "rodoviaria"}


def sugestoes() -> list[str]:
    return [c["pergunta_exemplo"] for c in _dados()["cenarios"] if c["id"] in _SUGERIDOS]


def documentos() -> list[DocumentoOut]:
    return [DocumentoOut(**{k: d[k] for k in DocumentoOut.model_fields}) for d in _dados()["documentos"]]


def documento(doc_id: str) -> dict | None:
    return next((d for d in _dados()["documentos"] if d["id"] == doc_id), None)
