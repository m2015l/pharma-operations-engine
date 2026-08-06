# Diário de Bordo — Solufarma Módulo 2

> Registro cronológico do trabalho. Cada sessão de trabalho relevante ganha uma entrada no topo (mais recente primeiro).
> Formato: data, quem trabalhou, o que foi feito, o que aprendemos, próximos passos.

---

## 2026-08-05 — Frente RAG & Agente: primeira fatia implementada (Roger + Claude)

**O que foi feito** (branch `feature/rag-agente`, ainda não mergeada):
- Pacote `src/solufarma_rag/` com chunking estrutural, pipeline incremental de embeddings, busca híbrida (vetorial + léxica + RRF) e agente com contrato de citação obrigatória;
- Toda dependência externa é injetável (Protocols): `FakeEmbeddingProvider`, `InMemoryChunkRepository` e `FakeLLM` permitem rodar tudo offline, sem Supabase e sem chaves de API;
- CLIs em `tools/chunk_document.py` e `tools/generate_embeddings.py`;
- Rascunho da RPC `busca_hibrida` em SQL — **entrega para a frente de Dados & Infra**, não aplicar daqui;
- 56 testes pytest offline + ruff limpo.

**Revisão dupla por agentes (revisor de código + guardião de escopo). Bugs reais encontrados e corrigidos:**
1. **Resposta sem nenhuma citação passava como sucesso** — quebrava o requisito central de rastreabilidade. `RespostaAgente` ganhou `contrato_citacao_ok` e `citacoes_invalidas`, com log de erro;
2. **Chunks estouravam o teto de tokens** (1143 contra teto de 1000): a contabilidade somava `estimar_tokens` por peça, e o arredondamento da divisão inteira acumulava; o prefixo contextual também não entrava no orçamento. Passou a ser contabilidade em caracteres;
3. **A busca nunca voltava vazia** — sem piso de similaridade, o agente jamais diria "não encontrei no acervo" e o loop de refinamento era código morto;
4. **O provedor fake de embeddings mentia** — com 64 dimensões, colisões de hash davam similaridade alta a textos sem palavra em comum; subido para 1024 (igual à produção);
5. Menores: JSON com BOM quebrava o CLI (Windows grava BOM), trecho da citação era dominado pelo prefixo, import de símbolo privado entre módulos (extraído para `text_utils.py`), divergências entre o Python e o rascunho SQL.

**Aprendizados:**
- Testes com tolerância folgada não pegam bugs: o teste do teto de tokens aceitava 2× o limite e por isso não viu o estouro de 14%;
- Um test double mal dimensionado inverte o resultado dos testes que deveria sustentar;
- Vale rodar revisão de escopo junto com a de código — foi ela que pegou a questão contratual do LangChain, que nenhuma revisão técnica apontaria.

**Pendências abertas por esta sessão** (ver PLANO_PROJETO.md, itens 8–12):
- 🔴 **LangChain**: o código não usa a biblioteca, mas ela é item explícito dos entregáveis contratados. **Decisão da equipe/Diva antes do merge** — não é escolha técnica isolada;
- 🔴 Duas lacunas no DDL bloqueiam o `SupabaseChunkRepository` (frente de Dados & Infra);
- Piso de similaridade precisa de recalibração com embeddings reais;
- Golden set de avaliação ainda não existe (depende de casos reais da Solufarma).

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
