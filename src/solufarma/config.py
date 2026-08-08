"""
config.py — Configuração central e validação de ambiente.

DECISÃO DE PROJETO (não estava no BRIEFING, registrada aqui conforme pedido):
o BRIEFING pede que `config.py` "valide a presença de cada variável na
importação". Validar TODAS na importação impediria rodar o M1 antes de existir
conta na Voyage e no Supabase — que só entram no M3.

Solução: as variáveis são agrupadas por ESTÁGIO e a validação é sob demanda,
via `exigir("extracao")`. Cada CLI chama `exigir()` do seu estágio na primeira
linha, então a falha continua acontecendo ANTES de qualquer trabalho caro —
que é o objetivo real do requisito ("nada de KeyError cru no meio de um lote
de 20 documentos") — sem acoplar marcos que não dependem um do outro.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------
# Diretórios
# --------------------------------------------------------------------------

RAIZ = Path(__file__).resolve().parents[2]

DIR_BRUTOS = Path(os.getenv("SOLUFARMA_DIR_BRUTOS", RAIZ / "data" / "brutos"))
DIR_EXTRAIDOS = Path(os.getenv("SOLUFARMA_DIR_EXTRAIDOS", RAIZ / "data" / "extraidos"))
DIR_CHUNKS = Path(os.getenv("SOLUFARMA_DIR_CHUNKS", RAIZ / "data" / "chunks"))
DIR_RELATORIOS = Path(os.getenv("SOLUFARMA_DIR_RELATORIOS", RAIZ / "data" / "relatorios"))
DIR_CACHE = Path(os.getenv("SOLUFARMA_DIR_CACHE", RAIZ / ".cache_ocr"))


# --------------------------------------------------------------------------
# OpenRouter / OCR
# --------------------------------------------------------------------------

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELO = os.getenv("OPENROUTER_MODELO", "anthropic/claude-sonnet-5")

# Preço em US$ por milhão de tokens. Vem do ambiente porque está atrelado ao
# slug: trocar de modelo sem trocar o preço faz o relatório de custo mentir.
PRECO_ENTRADA_USD_MTOK = float(os.getenv("OPENROUTER_PRECO_ENTRADA", "3.00"))
PRECO_SAIDA_USD_MTOK = float(os.getenv("OPENROUTER_PRECO_SAIDA", "15.00"))

# Claude reduz imagens para no máximo ~1568px no lado maior; renderizar acima
# disso só queima banda. Abaixo de ~1300px, tabela densa começa a errar dígito.
LADO_MAIOR_PX = int(os.getenv("SOLUFARMA_LADO_MAIOR_PX", "1500"))
JPEG_QUALIDADE = int(os.getenv("SOLUFARMA_JPEG_QUALIDADE", "88"))

# --- Roteamento: a dupla condição do invariante 2 do CLAUDE.md -------------
# Uma página só é "digital" se passar nas DUAS. Os 347 caracteres do carimbo
# do CAU numa folha A4 dão densidade ~0.00005 char/px² e reprovam na segunda.
# LIMIARES SÃO HIPÓTESE até o M2 confirmá-los sobre 20 documentos.
MIN_CARACTERES_UTEIS = int(os.getenv("SOLUFARMA_MIN_CARACTERES", "220"))
MIN_DENSIDADE = float(os.getenv("SOLUFARMA_MIN_DENSIDADE", "0.00035"))

# Linha presente em mais de X% das páginas é cabeçalho/rodapé/carimbo.
LIMIAR_BOILERPLATE = float(os.getenv("SOLUFARMA_LIMIAR_BOILERPLATE", "0.55"))

# Abaixo disso a página entra no relatório para revisão manual.
LIMIAR_CONFIANCA_REVISAO = float(os.getenv("SOLUFARMA_LIMIAR_CONFIANCA", "0.75"))

WORKERS = int(os.getenv("SOLUFARMA_WORKERS", "6"))
TENTATIVAS = int(os.getenv("SOLUFARMA_TENTATIVAS", "4"))
TIMEOUT_S = int(os.getenv("SOLUFARMA_TIMEOUT", "180"))


# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------

# ~4 chars por token em português. 2800 chars ≈ 700 tokens.
ALVO_CHARS = int(os.getenv("SOLUFARMA_ALVO_CHARS", "2800"))
MIN_CHARS = int(os.getenv("SOLUFARMA_MIN_CHARS", "350"))
OVERLAP_CHARS = int(os.getenv("SOLUFARMA_OVERLAP_CHARS", "250"))
LINHAS_POR_CHUNK_TABELA = int(os.getenv("SOLUFARMA_LINHAS_TABELA", "18"))


# --------------------------------------------------------------------------
# Validação por estágio
# --------------------------------------------------------------------------

VARIAVEIS_POR_ESTAGIO: dict[str, list[str]] = {
    "extracao": ["OPENROUTER_API_KEY"],
    "indexacao": ["VOYAGE_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_KEY"],
}


class ConfiguracaoInvalida(RuntimeError):
    """Ambiente incompleto para o estágio pedido."""


def exigir(estagio: str) -> None:
    """
    Valida as variáveis do estágio. Chame na PRIMEIRA linha de cada CLI, antes
    de abrir arquivo ou gastar chamada paga.

    Levanta ConfiguracaoInvalida nomeando cada variável faltante e apontando o
    caminho do .env — nunca um KeyError cru no meio de um lote.
    """
    if estagio not in VARIAVEIS_POR_ESTAGIO:
        raise ConfiguracaoInvalida(
            f"Estágio desconhecido: {estagio!r}. "
            f"Conhecidos: {', '.join(sorted(VARIAVEIS_POR_ESTAGIO))}"
        )

    faltantes = [v for v in VARIAVEIS_POR_ESTAGIO[estagio] if not os.getenv(v)]
    if not faltantes:
        return

    lista = "\n".join(f"  - {v}" for v in faltantes)
    raise ConfiguracaoInvalida(
        f"Faltam variáveis de ambiente para o estágio '{estagio}':\n{lista}\n\n"
        f"Copie .env.example para .env e preencha:\n"
        f"  cp .env.example .env\n\n"
        f"O .env esperado fica em: {RAIZ / '.env'}"
    )


def chave(nome: str) -> str:
    """Lê uma variável obrigatória já validada por `exigir()`."""
    valor = os.getenv(nome)
    if not valor:
        raise ConfiguracaoInvalida(
            f"Variável {nome} não definida. Chame config.exigir() antes de usá-la."
        )
    return valor


def criar_diretorios() -> None:
    """Cria a árvore de dados. Idempotente."""
    for d in (DIR_BRUTOS, DIR_EXTRAIDOS, DIR_CHUNKS, DIR_RELATORIOS, DIR_CACHE):
        d.mkdir(parents=True, exist_ok=True)


def resumo() -> str:
    """Texto de diagnóstico — usado pelos CLIs no cabeçalho da execução."""
    return (
        f"modelo={OPENROUTER_MODELO} "
        f"preço=${PRECO_ENTRADA_USD_MTOK}/${PRECO_SAIDA_USD_MTOK} por MTok | "
        f"roteamento: min_chars={MIN_CARACTERES_UTEIS} min_densidade={MIN_DENSIDADE}"
    )
