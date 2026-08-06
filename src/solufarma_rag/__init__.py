"""Pacote backend do assistente de IA para validação de licitações (Solufarma Módulo 2).

Estrutura (ver docs/ARQUITETURA.md §6):
- db/         modelos Pydantic e repositórios (Supabase real + em memória para testes)
- ingestion/  chunking estrutural e geração de embeddings
- retrieval/  busca híbrida (vetorial + full-text + filtros) com fusão RRF
- agent/      agente com contrato de citação obrigatória
- text_utils  normalização/tokenização compartilhada entre ingestão e retrieval

Nota: a orquestração do agente está em Python puro, sem LangChain/LangGraph —
decisão PENDENTE de validação da equipe (pendência P4 em docs/DECISOES.md), pois
o pipeline com LangChain é item explícito dos entregáveis contratados.
Ver a justificativa técnica em agent/agent.py.
"""

__version__ = "0.1.0"
