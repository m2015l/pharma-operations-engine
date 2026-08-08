"""
Pipeline de ingestão do acervo Solufarma.

Camadas (framework WAT, conforme CLAUDE.md):
    src/solufarma/  -> a lógica (este pacote)
    tools/*.py      -> CLIs finos que importam esta lógica
    workflows/*.md  -> SOPs que descrevem quando e como rodar cada CLI

Ordem do pipeline:
    formatos  -> descobre o formato real e rende as páginas
    extracao  -> roteia página a página e transcreve via VLM quando preciso
    chunking  -> costura o fluxo e corta por regime de conteúdo
    indexacao -> embeddings + upsert no Supabase (M3)
"""

__version__ = "0.1.0"
