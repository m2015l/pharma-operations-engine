# Solufarma – Módulo 2: Assistente de IA para Validação de Licitações

Projeto da **ITA Júnior** para a **Solufarma Engenharia**: assistente de inteligência artificial customizado para validação de licitações, apoiado em uma arquitetura de dados que ingere, processa e disponibiliza o acervo histórico de editais, atas e resultados.

## O que o sistema faz

- Ingere o acervo histórico de licitações (editais, atas, resultados) em **Supabase / PostgreSQL**;
- Aplica **OCR** em PDFs e documentos escaneados;
- Classifica e sumariza documentos via IA;
- Indexa tudo em uma **base vetorial** para busca por similaridade semântica;
- Responde consultas em linguagem natural via **pipeline RAG (LangChain)** integrado às APIs **Claude / OpenAI**, sempre citando as fontes originais;
- Analisa novos editais contra o acervo já validado;
- Interface web em **Streamlit** com chat e upload de editais.

## Cronograma macro (14 semanas)

| Fase | Semanas | Entrega |
|------|---------|---------|
| Infraestrutura e Dados | 1–4 | Base estruturada, pesquisável e pronta para alimentar a IA |
| Agente de IA e Vetorização | 5–9 | O "cérebro" da Solufarma: inteligência consultável em linguagem natural |
| Interface, Validação e Handoff | 10–12 | Ferramenta pronta para uso diário pela equipe |
| Suporte Pós-Entrega | 13–14 | Ajustes finos, correções e consolidação da rotina de uso |

Plano completo: [docs/PLANO_PROJETO.md](docs/PLANO_PROJETO.md) · Arquitetura: [docs/ARQUITETURA.md](docs/ARQUITETURA.md)

## Estrutura do repositório

```
acesso/         # Documentos de referência do projeto (proposta, timeline)
AGENTS/         # Definições de agentes de IA auxiliares do desenvolvimento
Skills/         # Skills do Claude Code criadas para este projeto
docs/           # Documentação viva: plano, arquitetura, decisões, diário de bordo
tools/          # Scripts Python determinísticos (OCR, ingestão, embeddings...)
workflows/      # SOPs em markdown (framework WAT)
.tmp/           # Arquivos temporários regeneráveis (fora do git)
.env            # Chaves de API e segredos (fora do git — ver .env.example)
```

## Setup rápido

1. Clone o repositório e crie um ambiente virtual Python 3.11+:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate    # Windows
   pip install -r requirements.txt
   ```
2. Copie `.env.example` para `.env` e preencha as chaves (Supabase, Anthropic/OpenAI).
3. Rode os testes — eles funcionam **sem** Supabase e sem chaves de API:
   ```bash
   .venv/Scripts/python.exe -m pytest              # 56 testes offline
   .venv/Scripts/python.exe -m ruff check src/ tests/ tools/
   ```
4. Consulte [docs/DIARIO_DE_BORDO.md](docs/DIARIO_DE_BORDO.md) para o estado atual do trabalho.

## Onde está o quê

| Você quer... | Leia |
|---|---|
| Entender o estado atual do trabalho | [docs/DIARIO_DE_BORDO.md](docs/DIARIO_DE_BORDO.md) |
| Mexer no pipeline RAG ou no agente | [docs/FRENTE_RAG.md](docs/FRENTE_RAG.md) |
| Ver o escopo e o que falta fazer | [docs/PLANO_PROJETO.md](docs/PLANO_PROJETO.md) |
| Entender a arquitetura técnica | [docs/ARQUITETURA.md](docs/ARQUITETURA.md) |
| Saber por que algo foi decidido assim | [docs/DECISOES.md](docs/DECISOES.md) |
| Executar um procedimento (SOPs) | [workflows/](workflows/) |

## Equipe

4 integrantes — papéis e divisão de responsabilidades em [docs/EQUIPE.md](docs/EQUIPE.md).

## Convenções de trabalho

- Todo avanço relevante é registrado em [docs/DIARIO_DE_BORDO.md](docs/DIARIO_DE_BORDO.md);
- Decisões técnicas importantes viram entrada em [docs/DECISOES.md](docs/DECISOES.md);
- Branches: `main` protegida; trabalhe em `feature/<nome-curto>` e abra PR;
- Segredos **somente** no `.env` (nunca commitados).
