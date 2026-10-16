# Equipe — Pharma Operations Platform · Enterprise Vendor Hub

> Estrutura de papéis e responsabilidades técnicas do projeto.

## Integrantes e Papéis

| Papel | Frente de trabalho | Responsabilidade Principal |
|-------|--------------------|----------------------------|
| Tech Lead / Project Manager | Coordenação geral | Gestão de escopo, priorização e alinhamento arquitetural |
| Engenheiro(a) de Dados | Dados & Infraestrutura | Supabase, modelagem PostgreSQL/pgvector, ingestão do acervo |
| Engenheiro(a) de IA / ML | OCR & Processamento | Rotinas de OCR/VLM, classificação/sumarização via IA, chunking |
| Engenheiro(a) de IA / RAG | RAG & Agente | Embeddings, busca híbrida, reranking, orquestração e prompts |
| Engenheiro(a) Full-Stack | Interface & API | Frontend Next.js, API FastAPI, exportação .docx e UX |

## Divisão por frente de trabalho

1. **Dados & Infraestrutura** — Supabase, modelagem do banco, ingestão do acervo, limpeza/padronização (peso maior nas semanas 1–4);
2. **OCR & Processamento de documentos** — rotinas de OCR, classificação/sumarização via IA, extração de metadados (semanas 1–5);
3. **RAG & Agente** — embeddings, base vetorial, pipeline LangChain, integração LLM, engenharia de prompts (semanas 4–10);
4. **Interface & Qualidade** — frontend Next.js + API FastAPI, testes com casos reais, documentação, handoff operacional (semanas 8–12).

Todas as frentes colaboram na engenharia de prompts e nos testes de validação (semanas 9–12).

## Rotina de trabalho

- **Branch `main` protegida**: mudanças entram por Pull Request com pelo menos 1 revisão;
- **Branches**: `feature/<nome-curto>`, `fix/<nome-curto>`;
- **Registro**: quem fecha uma frente de trabalho relevante adiciona entrada no `DIARIO_DE_BORDO.md`;
- **Sincronização**: check-in semanal curto para atualizar os checkboxes do `PLANO_PROJETO.md`.
