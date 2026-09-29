"""
modelos.py — Estruturas de dados que atravessam o pipeline.

Ficam isoladas porque `extracao` escreve o JSON e `chunking`/`calibracao` leem
o mesmo JSON. Mudar um campo aqui é mudar o contrato entre os três estágios.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Pagina:
    """Uma página transcrita. `markdown` é a entrada do chunking."""

    numero: int
    estrategia: str = "pendente"  # nativo | vlm | vazia
    markdown: str = ""
    secao_corrente: str | None = None
    cabecalho_tabela_final: list[str] | None = None
    tabela_aberta_no_fim: bool = False
    confianca: float = 1.0
    observacoes: str = ""
    tokens_entrada: int = 0
    tokens_saida: int = 0
    # Área em pixels² usada no cálculo de densidade. Guardada para o M2 poder
    # auditar o roteamento sem re-renderizar o documento.
    area_px: int = 0
    caracteres_uteis: int = 0


@dataclass
class Documento:
    arquivo: str
    hash_documento: str
    n_paginas: int
    formato_detectado: str
    modelo: str = ""
    boilerplate_removido: list[str] = field(default_factory=list)
    paginas: list[Pagina] = field(default_factory=list)
    custo_estimado_usd: float = 0.0
    # Chamadas que realmente saíram para a API (cache não conta). É o número
    # que prova a idempotência exigida pelo CLAUDE.md.
    chamadas_pagas: int = 0
    chamadas_cache: int = 0

    @property
    def n_nativas(self) -> int:
        return sum(1 for p in self.paginas if p.estrategia == "nativo")

    @property
    def n_vlm(self) -> int:
        return sum(1 for p in self.paginas if p.estrategia in ("vlm", "vazia"))

    @property
    def tokens_entrada(self) -> int:
        return sum(p.tokens_entrada for p in self.paginas)

    @property
    def tokens_saida(self) -> int:
        return sum(p.tokens_saida for p in self.paginas)


@dataclass
class Bloco:
    """Trecho homogêneo do fluxo costurado, já com o caminho de seção."""

    tipo: str  # prosa | tabela
    linhas: list[str]
    caminho: list[str]
    pag_ini: int
    pag_fim: int
    # Página de cada linha (paralelo a `linhas`). Um bloco longo atravessa
    # dezenas de páginas; sem isto, todo chunk dele citaria a página do início
    # do bloco. Vazio = sem informação, vale pag_ini/pag_fim do bloco.
    paginas_linhas: list[int] = field(default_factory=list)


@dataclass
class Chunk:
    id: str
    texto: str  # com cabeçalho contextual — vai para o embedding
    texto_puro: str  # sem cabeçalho — exibido ao usuário
    tipo: str  # prosa | tabela | metadados
    caminho_secao: list[str] = field(default_factory=list)
    pagina_inicio: int = 0
    pagina_fim: int = 0
    n_chars: int = 0
    documento: str = ""
    # True quando o corte veio do limite de tamanho e não de uma fronteira de
    # seção. É a métrica D do relatório de calibração (M2).
    cortado_por_tamanho: bool = False
    metadados: dict = field(default_factory=dict)
