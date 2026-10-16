---
name: registro-projeto
description: Registra o progresso do trabalho no projeto Pharma Operations Platform - atualiza o diário de bordo, marca checkboxes do plano e cria ADRs de decisões. Use ao final de uma sessão de trabalho, quando o usuário pedir para "registrar o progresso", "atualizar o diário" ou "documentar a decisão".
---

# Registro de Progresso do Projeto

Você vai registrar o trabalho feito na sessão atual nos documentos vivos do projeto. Sempre em **português brasileiro**.

## Passos

1. **Revise o que aconteceu na sessão**: o que foi implementado, decidido, aprendido ou quebrado.

2. **Atualize `docs/DIARIO_DE_BORDO.md`**:
   - Adicione uma nova entrada NO TOPO (abaixo do cabeçalho, mais recente primeiro);
   - Formato: `## AAAA-MM-DD — <título curto> (<quem>)` com seções **O que foi feito**, **Aprendizados / observações**, **Próximos passos**;
   - Seja específico: cite arquivos, ferramentas e resultados de testes.

3. **Atualize `docs/PLANO_PROJETO.md`**:
   - Marque `[x]` nos itens concluídos;
   - Atualize a tabela de pendências (feche resolvidas, adicione novas).

4. **Se houve decisão técnica relevante**, adicione um ADR em `docs/DECISOES.md`:
   - Numeração sequencial (ADR-00N);
   - Campos: Data, Status, Contexto, Decisão, Justificativa, Consequências;
   - Se a decisão resolve uma "decisão pendente" (P1–P4...), remova-a da tabela de pendentes.

5. **Não invente progresso**: registre apenas o que de fato aconteceu e foi verificado. Se um teste falhou, registre a falha.

## Critério de qualidade

Um membro do time que não participou da sessão deve conseguir entender o estado do projeto lendo apenas o diário e o plano.
