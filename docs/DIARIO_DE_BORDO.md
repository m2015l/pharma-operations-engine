# Diário de Bordo — Solufarma Módulo 2

> Registro cronológico do trabalho. Cada sessão de trabalho relevante ganha uma entrada no topo (mais recente primeiro).
> Formato: data, quem trabalhou, o que foi feito, o que aprendemos, próximos passos.

---

## 2026-08-05 — Respostas do kickoff e primeiros workflows (Roger + Claude)

**O que foi feito:**
- Roger respondeu as pendências do kickoff: editais entrarão **via upload no frontend Streamlit** e ficarão no Supabase (ADR-003); conta Supabase já existe (chaves LLM virão depois); cronograma sem datas absolutas (ADR-004); nomes da equipe registrados em `EQUIPE.md` (Diva — gerente; Sparrow, Bia, Mosquitão);
- Criados os dois primeiros workflows WAT: `workflows/ingestao_documento.md` e `workflows/geracao_embeddings.md` (com tabelas de tools a implementar);
- Tabela de pendências do `PLANO_PROJETO.md` atualizada.

**Aprendizados / observações:**
- A ingestão via Streamlit antecipa parte da interface: uma versão mínima de upload precisa existir já na fase de dados (consequência registrada no ADR-003);
- Falta confirmar o GitHub dos integrantes e se algum apelido corresponde ao próprio Roger.

**Próximos passos:**
- Obter credenciais do Supabase existente e preencher `.env`;
- Habilitar pgvector e aplicar o DDL inicial (docs/ARQUITETURA.md §3);
- Implementar `tools/ingest_document.py` e `tools/extract_text.py` (podem começar antes das chaves LLM: upload, hash, triagem e extração nativa não dependem de LLM);
- Push do commit inicial (aguardando confirmação do Roger).

---

## 2026-08-04 — Setup inicial do projeto (Roger + Claude)

**O que foi feito:**
- Leitura e análise da proposta/timeline da ITA Júnior (PDF em `acesso/`);
- Criação da estrutura completa do repositório (docs, tools, workflows, Skills, .tmp);
- Documentos de registro criados: `PLANO_PROJETO.md`, `ARQUITETURA.md`, `DECISOES.md`, `EQUIPE.md` e este diário;
- `README.md`, `.gitignore`, `.env.example` e `requirements.txt` iniciais;
- Agente `ai-engineer` registrado em `.claude/agents/` e usado para redigir a arquitetura técnica;
- Skills de apoio criadas em `Skills/`;
- Repositório git inicializado e conectado a `https://github.com/RgNN988/Solufarma_Mod_2`.

**Aprendizados / observações:**
- O repositório remoto estava vazio — este commit é o marco zero do projeto;
- A pasta do projeto está dentro do OneDrive: atenção a possíveis conflitos de sincronização com o git (avaliar mover para fora do OneDrive se houver problemas).

**Próximos passos:**
- Resolver as pendências da tabela em `PLANO_PROJETO.md` (acervo, Supabase, chaves de API, papéis da equipe);
- Definir data oficial de início da semana 1;
- Montar ambiente Python e validar `requirements.txt`.

---
