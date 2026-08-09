# Atalhos do pipeline de ingestão.
#
# `make` NÃO está instalado no Windows por padrão. Cada alvo abaixo tem o
# equivalente direto em `uv run` — use esse se não tiver make:
#
#   make setup    ->  uv sync --extra dev
#   make extrair  ->  uv run python tools/extract_text.py
#   make chunks   ->  uv run python tools/chunk_document.py
#   make testar   ->  uv run pytest
#   make lint     ->  uv run ruff check src tests tools

.PHONY: setup extrair chunks calibrar indexar banco testar lint limpar-cache

setup:
	uv sync --extra dev
	@echo "Pronto. Copie .env.example para .env e preencha OPENROUTER_API_KEY."

extrair:
	uv run python tools/extract_text.py

chunks:
	uv run python tools/chunk_document.py

calibrar:
	@echo "M2 ainda não implementado — ver BRIEFING.md."

indexar:
	@echo "M3 ainda não implementado. Banco e repositório prontos e validados;"
	@echo "falta a ponte chunking -> Supabase. Especificação: workflows/indexacao.md"

# Diagnóstico e smoke test do Supabase (schema + repositório contra o banco real).
banco:
	uv run python tools/setup_supabase.py --check --smoke

testar:
	uv run pytest -v

lint:
	uv run ruff check src tests tools

# Apaga o cache de OCR. Use só quando quiser reprocessar de verdade —
# a próxima execução vai custar dinheiro novamente.
limpar-cache:
	rm -rf .cache_ocr
	@echo "Cache apagado. A próxima extração fará chamadas pagas."
