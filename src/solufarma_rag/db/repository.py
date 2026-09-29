"""Repositórios de chunks: protocolo injetável + implementação em memória.

O Supabase real ainda não tem credenciais provisionadas (frente de Dados &
Infraestrutura). Por isso a camada de acesso a banco é um Protocol: o pipeline
de embeddings e a busca híbrida funcionam contra qualquer implementação —
`InMemoryChunkRepository` nos testes/desenvolvimento, `SupabaseChunkRepository`
quando o banco estiver provisionado (DDL em docs/ARQUITETURA.md §3).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from pydantic import BaseModel

from ..text_utils import normalizar as _normalizar
from ..text_utils import tokenizar as _tokenizar
from .models import Chunk, ItemPlanilha


def _contem(a: object, b: object) -> bool:
    """Semântica do `@>` do JSONB em Python: `a` contém `b`?

    Objeto: toda chave de `b` existe em `a` e o valor de `a` contém o de `b`.
    Lista: todo elemento de `b` é contido por ALGUM elemento de `a`.
    Escalar: igualdade. Espelha o SQL para o repositório em memória.
    """
    if isinstance(b, dict):
        return isinstance(a, dict) and all(k in a and _contem(a[k], v) for k, v in b.items())
    if isinstance(b, list):
        return isinstance(a, list) and all(any(_contem(x, y) for x in a) for y in b)
    return a == b


class FiltrosBusca(BaseModel):
    """Filtros por metadados aplicados ANTES do ranking (ARQUITETURA.md §5.1).

    `executante_grupo` e `disciplinas` filtram pela classificação por IA do
    documento (`documentos.classificacao`, migração 004, formato
    `{"campo": {"valor": ...}}` de `solufarma.classificacao`). Com um deles
    preenchido, documento SEM classificação fica fora da busca (não há como
    saber o executante dele); sem nenhum dos dois, nada muda. `disciplinas`
    com mais de um valor exige TODAS (containment do JSONB).
    """

    orgao: str | None = None
    tipo_documento: str | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    executante_grupo: str | None = None
    disciplinas: list[str] | None = None

    def classificacao_exigida(self) -> dict | None:
        """O documento-alvo do `classificacao @> ...`, ou None se não há filtro de classificação."""
        alvo: dict = {}
        if self.executante_grupo:
            alvo["executante_grupo"] = {"valor": self.executante_grupo}
        if self.disciplinas:
            alvo["disciplinas"] = [{"valor": d} for d in self.disciplinas]
        return alvo or None

    def aceita_classificacao(self, classificacao: dict | None) -> bool:
        """Mesma regra do SQL: sem filtro aceita tudo; com filtro, exige containment."""
        alvo = self.classificacao_exigida()
        if alvo is None:
            return True
        return classificacao is not None and _contem(classificacao, alvo)

    def aceita(self, chunk: Chunk) -> bool:
        """Verifica se um chunk passa nos filtros (usado pelo repositório em memória)."""
        if self.tipo_documento and chunk.tipo_documento != self.tipo_documento:
            return False
        if self.orgao and _normalizar(self.orgao) not in _normalizar(chunk.orgao):
            return False
        if self.data_inicio and (chunk.data is None or chunk.data < self.data_inicio):
            return False
        return not (self.data_fim and (chunk.data is None or chunk.data > self.data_fim))


class ChunkRepository(Protocol):
    """Contrato mínimo que o pipeline de embeddings e a busca híbrida exigem."""

    def upsert_chunks(self, chunks: list[Chunk]) -> None:
        """Insere/atualiza chunks (chave natural: documento_id + chunk_index)."""
        ...

    def listar_pendentes(self) -> list[Chunk]:
        """Chunks sem embedding OU cujo content_hash mudou desde a última indexação."""
        ...

    def salvar_embedding(
        self, chunk_chave: str, embedding: list[float], embedding_model: str
    ) -> None:
        """Grava o embedding registrando o modelo usado e o hash embeddado."""
        ...

    def marcar_documento_indexado(self, documento_id: str) -> None:
        """status_processamento do documento → 'indexado' (workflow geracao_embeddings)."""
        ...

    def documentos_com_pendencias(self) -> set[str]:
        """IDs de documentos que ainda têm chunks sem embedding atualizado."""
        ...

    def buscar_vetorial(
        self,
        embedding_consulta: list[float],
        filtros: FiltrosBusca,
        limite: int,
        similaridade_minima: float = 0.0,
    ) -> list[tuple[Chunk, float]]:
        """Similaridade de cosseno (no Supabase: índice HNSW do pgvector).

        `similaridade_minima` é o piso de relevância: sem ele a busca vetorial
        devolve sempre os `limite` chunks mais próximos, por mais distantes que
        sejam — e o agente passaria a "responder" perguntas fora do acervo com
        contexto irrelevante. Ver nota em retrieval/hybrid_search.py.
        """
        ...

    def buscar_textual(
        self, consulta: str, filtros: FiltrosBusca, limite: int
    ) -> list[tuple[Chunk, float]]:
        """Busca léxica (no Supabase: FTS 'portuguese' + unaccent)."""
        ...

    def buscar_itens_planilha(
        self, termo: str, documento_id: str | None = None, limite: int = 20
    ) -> list[ItemPlanilha]:
        """SELECT estruturado sobre `itens_planilha` (I9, PRECISÃO.md).

        `itens_planilha` tem centenas de linhas populadas e, sem este método,
        nunca é consultada: perguntas de quantitativo dependem só do retrieval
        vetorial/léxico sobre o texto corrido da tabela, quando um `ilike`
        exato resolveria. NÃO agrega/soma — o formato desta planilha coloca a
        descrição numa linha e a quantidade na seguinte, por bitola, então um
        SUM ingênuo dá número errado com cara de certo. Lista as linhas
        casadas; agregação fica para quando houver um segundo documento para
        validar o formato.

        O casamento é só contra `celulas` (a linha em si), não contra `secao`
        — uma consulta como "gases" só acha a linha se a palavra estiver na
        própria célula (ex.: descrição do item), não só no rótulo de seção que
        a envolve. Escreva `termo` com vocabulário que apareceria na CÉLULA.
        """
        ...


# ---------------------------------------------------------------------------
# Implementação em memória (testes e desenvolvimento offline)
# ---------------------------------------------------------------------------


def _validar_lote_documento(documento_id: str, chunks: list[Chunk]) -> set[int]:
    """Guarda da reindexação: lote não vazio, todo do mesmo documento, sem índice repetido.

    Lote vazio é recusado de propósito — "substituir por nada" apagaria o
    documento inteiro, e isso nunca é o que uma reindexação quer.
    """
    if not chunks:
        raise ValueError("lote vazio: substituir por nada apagaria todos os chunks do documento")
    outros = {c.documento_id for c in chunks} - {documento_id}
    if outros:
        raise ValueError(f"lote mistura documentos: {sorted(outros)} além de {documento_id}")
    indices = [c.chunk_index for c in chunks]
    if len(set(indices)) != len(indices):
        raise ValueError("lote com chunk_index repetido")
    return set(indices)


def _cosseno(a: list[float], b: list[float]) -> float:
    """Similaridade de cosseno entre dois vetores de mesma dimensão."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


@dataclass
class _RegistroChunk:
    """Linha interna do repositório em memória (chunk + estado de indexação)."""

    chunk: Chunk
    embedding: list[float] | None = None
    embedding_model: str | None = None
    embedding_content_hash: str | None = None


@dataclass
class InMemoryChunkRepository:
    """Repositório em memória com a mesma semântica esperada do Supabase.

    Implementa a lógica incremental: um chunk é "pendente" se nunca foi
    embeddado ou se o content_hash atual difere do hash embeddado.
    """

    _registros: dict[str, _RegistroChunk] = field(default_factory=dict)
    documentos_indexados: set[str] = field(default_factory=set)
    _itens_planilha: list[ItemPlanilha] = field(default_factory=list)
    # documento_id -> `documentos.classificacao` (jsonb). Ausente = não classificado.
    _classificacoes: dict[str, dict] = field(default_factory=dict)

    def definir_classificacao(self, documento_id: str, classificacao: dict) -> None:
        """Equivale ao `classificacao.salvar` do Supabase (testes)."""
        self._classificacoes[documento_id] = classificacao

    def contar_documentos_sem_classificacao(self) -> int:
        docs = {r.chunk.documento_id for r in self._registros.values()}
        return len(docs - set(self._classificacoes))

    def _passa(self, chunk: Chunk, filtros: FiltrosBusca) -> bool:
        return filtros.aceita(chunk) and filtros.aceita_classificacao(
            self._classificacoes.get(chunk.documento_id)
        )

    def _com_executante(self, chunk: Chunk) -> Chunk:
        """Anexa executante/grupo da classificação, como faz o JOIN do Supabase."""
        cls = self._classificacoes.get(chunk.documento_id)
        if not cls:
            return chunk
        return chunk.model_copy(
            update={
                "executante": (cls.get("executante") or {}).get("valor"),
                "executante_grupo": (cls.get("executante_grupo") or {}).get("valor"),
            }
        )

    def upsert_chunks(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            existente = self._registros.get(chunk.chave)
            if existente is None:
                self._registros[chunk.chave] = _RegistroChunk(chunk=chunk)
            else:
                # Mantém o embedding antigo: se o hash não mudou, não re-embedda.
                existente.chunk = chunk

    def substituir_chunks_documento(self, documento_id: str, chunks: list[Chunk]) -> int:
        """Upsert dos chunks + remoção dos órfãos do MESMO documento. Devolve removidos."""
        indices = _validar_lote_documento(documento_id, chunks)
        self.upsert_chunks(chunks)
        orfaos = [
            chave
            for chave, r in self._registros.items()
            if r.chunk.documento_id == documento_id and r.chunk.chunk_index not in indices
        ]
        for chave in orfaos:
            del self._registros[chave]
        return len(orfaos)

    def listar_pendentes(self) -> list[Chunk]:
        pendentes = [
            r.chunk
            for r in self._registros.values()
            if r.embedding is None or r.embedding_content_hash != r.chunk.content_hash
        ]
        return sorted(pendentes, key=lambda c: (c.documento_id, c.chunk_index))

    def salvar_embedding(
        self, chunk_chave: str, embedding: list[float], embedding_model: str
    ) -> None:
        registro = self._registros[chunk_chave]
        registro.embedding = embedding
        registro.embedding_model = embedding_model
        registro.embedding_content_hash = registro.chunk.content_hash

    def marcar_documento_indexado(self, documento_id: str) -> None:
        self.documentos_indexados.add(documento_id)

    def documentos_com_pendencias(self) -> set[str]:
        return {c.documento_id for c in self.listar_pendentes()}

    def buscar_vetorial(
        self,
        embedding_consulta: list[float],
        filtros: FiltrosBusca,
        limite: int,
        similaridade_minima: float = 0.0,
    ) -> list[tuple[Chunk, float]]:
        candidatos = [
            (self._com_executante(r.chunk), _cosseno(embedding_consulta, r.embedding))
            for r in self._registros.values()
            if r.embedding is not None and self._passa(r.chunk, filtros)
        ]
        candidatos = [par for par in candidatos if par[1] >= similaridade_minima]
        candidatos.sort(key=lambda par: par[1], reverse=True)
        return candidatos[:limite]

    def buscar_textual(
        self, consulta: str, filtros: FiltrosBusca, limite: int
    ) -> list[tuple[Chunk, float]]:
        termos = set(_tokenizar(consulta))
        if not termos:
            return []
        resultados: list[tuple[Chunk, float]] = []
        for r in self._registros.values():
            if not self._passa(r.chunk, filtros):
                continue
            tokens_chunk = _tokenizar(r.chunk.conteudo)
            if not tokens_chunk:
                continue
            acertos = sum(1 for t in tokens_chunk if t in termos)
            if acertos > 0:
                # Aproximação de ts_rank: frequência dos termos normalizada pelo tamanho.
                resultados.append((self._com_executante(r.chunk), acertos / len(tokens_chunk)))
        resultados.sort(key=lambda par: par[1], reverse=True)
        return resultados[:limite]

    def buscar_itens_planilha(
        self, termo: str, documento_id: str | None = None, limite: int = 20
    ) -> list[ItemPlanilha]:
        """Mesma semântica do `ilike` do Supabase: substring, sem acento/caixa."""
        termo_norm = _normalizar(termo)
        resultado = []
        for item in self._itens_planilha:
            if documento_id and item.documento_id != documento_id:
                continue
            if termo_norm and termo_norm not in _normalizar(" ".join(item.celulas)):
                continue
            resultado.append(item)
        return resultado[:limite]

    # Auxiliares para testes/inspeção -------------------------------------

    def obter_registro(self, chunk_chave: str) -> _RegistroChunk:
        return self._registros[chunk_chave]

    def total_chunks(self) -> int:
        return len(self._registros)

    def adicionar_item_planilha(self, item: ItemPlanilha) -> None:
        """Popula `itens_planilha` sem depender do pipeline de ingestão (testes)."""
        self._itens_planilha.append(item)


# ---------------------------------------------------------------------------
# Implementação real: Postgres/pgvector do Supabase
# ---------------------------------------------------------------------------

# `orgao` e `data_abertura` vivem em `licitacoes`, não em `doc_chunks` (decisão
# de DDL: não duplicar escrita). Todo SELECT que monta um Chunk completo passa
# por estes JOINs — daí a constante, para as três consultas não divergirem.
#
# Executante e grupo vêm da classificação por IA (migração 004) e ficam DEPOIS
# do score (índices 12 e 13) para não deslocar as colunas que já existiam.
# `{{` `}}` escapam as chaves do `.format(score=...)`.
_SELECT_CHUNK = """
    select c.documento_id, c.chunk_index, d.tipo, coalesce(l.orgao, '—') as orgao,
           l.data_abertura, coalesce(c.secao, '') as secao,
           c.pagina_inicio, c.pagina_fim, c.conteudo, c.token_count, c.content_hash,
           {score} as score,
           d.classificacao #>> '{{executante,valor}}' as executante,
           d.classificacao #>> '{{executante_grupo,valor}}' as executante_grupo
    from doc_chunks c
    join documentos d on d.id = c.documento_id
    left join licitacoes l on l.id = d.licitacao_id
"""

# Filtros por metadados aplicados ANTES do ranking (ARQUITETURA.md §5.1).
# Cada filtro é neutro quando o parâmetro é NULL, então a mesma SQL serve para
# qualquer combinação — sem montar string dinâmica (e sem risco de injeção).
_WHERE_FILTROS = """
    and (%(tipo)s::text is null or d.tipo = %(tipo)s)
    and (%(orgao)s::text is null or l.orgao ilike '%%' || %(orgao)s || '%%')
    and (%(data_inicio)s::date is null or l.data_abertura >= %(data_inicio)s)
    and (%(data_fim)s::date is null or l.data_abertura <= %(data_fim)s)
    and (%(classificacao)s::jsonb is null or d.classificacao @> %(classificacao)s::jsonb)
"""
# O último filtro é containment (`@>`) sobre `documentos.classificacao`, o
# operador que o GIN `jsonb_path_ops` da migração 004 atende. Com o parâmetro
# NULL (sem filtro), documento não classificado continua na busca; com filtro,
# `NULL @> x` é NULL e o documento não classificado sai — de propósito.


def _params_filtros(filtros: FiltrosBusca) -> dict:
    alvo = filtros.classificacao_exigida()
    return {
        "tipo": filtros.tipo_documento,
        "orgao": filtros.orgao,
        "data_inicio": filtros.data_inicio,
        "data_fim": filtros.data_fim,
        "classificacao": json.dumps(alvo, ensure_ascii=False) if alvo else None,
    }


def _linha_para_chunk(linha: tuple) -> Chunk:
    """Converte uma linha de `_SELECT_CHUNK` em Chunk (ordem das colunas importa)."""
    return Chunk(
        documento_id=str(linha[0]),
        chunk_index=linha[1],
        tipo_documento=linha[2],
        orgao=linha[3],
        data=linha[4],
        secao=linha[5],
        pagina_inicio=linha[6],
        pagina_fim=linha[7],
        conteudo=linha[8],
        token_count=linha[9],
        content_hash=linha[10],
        executante=linha[12] if len(linha) > 12 else None,
        executante_grupo=linha[13] if len(linha) > 13 else None,
    )


@dataclass
class SupabaseChunkRepository:
    """Repositório real sobre o Postgres/pgvector do Supabase.

    Recebe uma conexão psycopg já aberta (`criar_conexao()` monta a padrão a
    partir do DATABASE_URL). A conexão é injetada em vez de criada aqui para o
    chamador controlar transação e ciclo de vida — um CLI de ingestão quer uma
    conexão por execução, o Streamlit quer uma por sessão.

    A busca é feita em duas consultas (vetorial e léxica) fundidas por RRF em
    Python, no `HybridSearcher` — mesma implementação que os testes cobrem. Ver
    a nota em migrations/001_schema_inicial.sql sobre por que a RPC ficou de fora.
    """

    conn: object  # psycopg.Connection

    def upsert_chunks(self, chunks: list[Chunk]) -> None:
        """Insere/atualiza chunks pela chave natural (documento_id, chunk_index).

        NÃO limpa o embedding no update: quem decide o que reprocessar é a
        comparação `content_hash != embedding_content_hash` em listar_pendentes.
        Assim um reprocessamento de chunking que não mudou o texto (mesma seção,
        mesmo conteúdo) não força re-embedar o documento inteiro.

        NÃO remove chunks antigos: se o chunking novo gerar MENOS chunks, os de
        `chunk_index` maior sobram órfãos. Para reindexar um documento use
        `substituir_chunks_documento`.
        """
        if not chunks:
            return
        with self.conn.cursor() as cur:
            self._executar_upsert(cur, chunks)
        self.conn.commit()

    def substituir_chunks_documento(self, documento_id: str, chunks: list[Chunk]) -> int:
        """Reindexação de UM documento: upsert + remoção dos órfãos, numa transação.

        Apaga só linhas de `documento_id` cujo `chunk_index` não está no lote
        novo. Se qualquer passo falhar, rollback — o documento nunca fica com
        metade dos chunks. Devolve quantos órfãos foram removidos.
        """
        indices = _validar_lote_documento(documento_id, chunks)
        try:
            with self.conn.cursor() as cur:
                self._executar_upsert(cur, chunks)
                cur.execute(
                    """
                    delete from doc_chunks
                     where documento_id = %s
                       and not (chunk_index = any(%s))
                    """,
                    (documento_id, sorted(indices)),
                )
                removidos = cur.rowcount
        except Exception:
            self.conn.rollback()
            raise
        self.conn.commit()
        return removidos

    @staticmethod
    def _executar_upsert(cur, chunks: list[Chunk]) -> None:
        cur.executemany(
            """
            insert into doc_chunks (
                documento_id, chunk_index, secao, pagina_inicio, pagina_fim,
                conteudo, token_count, content_hash
            ) values (%s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (documento_id, chunk_index) do update set
                secao = excluded.secao,
                pagina_inicio = excluded.pagina_inicio,
                pagina_fim = excluded.pagina_fim,
                conteudo = excluded.conteudo,
                token_count = excluded.token_count,
                content_hash = excluded.content_hash
            """,
            [
                (
                    c.documento_id,
                    c.chunk_index,
                    c.secao,
                    c.pagina_inicio,
                    c.pagina_fim,
                    c.conteudo,
                    c.token_count,
                    c.content_hash,
                )
                for c in chunks
            ],
        )

    def listar_pendentes(self) -> list[Chunk]:
        """Sem embedding OU com content_hash diferente do que foi embeddado.

        `is distinct from` (e não `!=`) porque embedding_content_hash é NULL em
        chunk nunca indexado — e `NULL != texto` resulta em NULL, não em true.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                _SELECT_CHUNK.format(score="0.0")
                + """
                where c.embedding is null
                   or c.embedding_content_hash is distinct from c.content_hash
                order by c.documento_id, c.chunk_index
                """
            )
            return [_linha_para_chunk(linha) for linha in cur.fetchall()]

    def salvar_embedding(
        self, chunk_chave: str, embedding: list[float], embedding_model: str
    ) -> None:
        """Grava o embedding e marca QUAL hash foi embeddado (base do incremental)."""
        documento_id, chunk_index = chunk_chave.rsplit(":", 1)
        with self.conn.cursor() as cur:
            cur.execute(
                """
                update doc_chunks
                   set embedding = %s,
                       embedding_model = %s,
                       embedding_content_hash = content_hash
                 where documento_id = %s and chunk_index = %s
                """,
                (embedding, embedding_model, documento_id, int(chunk_index)),
            )
        self.conn.commit()

    def marcar_documento_indexado(self, documento_id: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "update documentos set status_processamento = 'indexado' where id = %s",
                (documento_id,),
            )
        self.conn.commit()

    def contar_documentos_sem_classificacao(self) -> int:
        """Quantos documentos com chunks ficam fora de uma busca com filtro de classificação."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                select count(*) from documentos d
                 where d.classificacao is null
                   and exists (select 1 from doc_chunks c where c.documento_id = d.id)
                """
            )
            return int(cur.fetchone()[0])

    def documentos_com_pendencias(self) -> set[str]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                select distinct documento_id from doc_chunks
                 where embedding is null
                    or embedding_content_hash is distinct from content_hash
                """
            )
            return {str(linha[0]) for linha in cur.fetchall()}

    def buscar_vetorial(
        self,
        embedding_consulta: list[float],
        filtros: FiltrosBusca,
        limite: int,
        similaridade_minima: float = 0.0,
    ) -> list[tuple[Chunk, float]]:
        """Similaridade de cosseno via índice HNSW do pgvector.

        `<=>` é a distância de cosseno; `1 - distância` é a similaridade. A
        ordenação usa o operador direto (e não a expressão de similaridade) para
        o planner conseguir usar o índice HNSW.
        """
        params = _params_filtros(filtros)
        params |= {
            "consulta": embedding_consulta,
            "minimo": similaridade_minima,
            "limite": limite,
        }
        with self.conn.cursor() as cur:
            cur.execute(
                _SELECT_CHUNK.format(score="1 - (c.embedding <=> %(consulta)s::vector)")
                + """
                where c.embedding is not null
                  and 1 - (c.embedding <=> %(consulta)s::vector) >= %(minimo)s
                """
                + _WHERE_FILTROS
                + """
                order by c.embedding <=> %(consulta)s::vector
                limit %(limite)s
                """,
                params,
            )
            return [(_linha_para_chunk(linha), float(linha[11])) for linha in cur.fetchall()]

    def buscar_textual(
        self, consulta: str, filtros: FiltrosBusca, limite: int
    ) -> list[tuple[Chunk, float]]:
        """Full-text 'portuguese' + unaccent, ranqueada por ts_rank.

        `websearch_to_tsquery` aceita a sintaxe que o usuário já conhece (aspas
        para frase exata, `-` para excluir) e, ao contrário de `to_tsquery`, não
        levanta erro com pontuação solta — o que importa num domínio cheio de
        códigos como "PE 045/2023".
        """
        params = _params_filtros(filtros)
        params |= {"consulta": consulta, "limite": limite}
        with self.conn.cursor() as cur:
            cur.execute(
                _SELECT_CHUNK.format(
                    score="ts_rank(c.fts, websearch_to_tsquery('portuguese', public.f_unaccent(%(consulta)s)))"
                )
                + """
                where c.fts @@ websearch_to_tsquery('portuguese', public.f_unaccent(%(consulta)s))
                """
                + _WHERE_FILTROS
                + """
                order by score desc
                limit %(limite)s
                """,
                params,
            )
            return [(_linha_para_chunk(linha), float(linha[11])) for linha in cur.fetchall()]

    def buscar_itens_planilha(
        self, termo: str, documento_id: str | None = None, limite: int = 20
    ) -> list[ItemPlanilha]:
        """`ilike` sobre `array_to_string(celulas, ' ')` (I9, PRECISÃO.md).

        NÃO EXECUTADO CONTRA O SUPABASE REAL nesta sessão (sem credenciais e
        fora de escopo — ver PRECISÃO.md I9 e I6). Coberto por teste apenas via
        `InMemoryChunkRepository`; a execução contra o banco real fica
        pendente de verificação manual.
        """
        params = {"termo": termo, "documento_id": documento_id, "limite": limite}
        with self.conn.cursor() as cur:
            cur.execute(
                """
                select ip.documento_id, coalesce(d.tipo, 'outro') as tipo,
                       coalesce(l.orgao, '—') as orgao, ip.pagina,
                       coalesce(ip.secao, '') as secao, ip.celulas
                from itens_planilha ip
                left join documentos d on d.id = ip.documento_id
                left join licitacoes l on l.id = d.licitacao_id
                where array_to_string(ip.celulas, ' ') ilike '%%' || %(termo)s || '%%'
                  and (%(documento_id)s::uuid is null or ip.documento_id = %(documento_id)s::uuid)
                order by ip.pagina nulls last
                limit %(limite)s
                """,
                params,
            )
            return [
                ItemPlanilha(
                    documento_id=str(linha[0]) if linha[0] else None,
                    tipo_documento=linha[1],
                    orgao=linha[2],
                    pagina=linha[3],
                    secao=linha[4],
                    celulas=list(linha[5]),
                )
                for linha in cur.fetchall()
            ]


def criar_conexao(database_url: str | None = None):
    """Abre conexão psycopg com o Postgres do Supabase, com pgvector registrado.

    O registro do tipo `vector` é o que permite passar `list[float]` direto como
    parâmetro e receber listas de volta — sem ele o driver manda o vetor como
    string e o Postgres recusa.

    Import tardio: psycopg e pgvector só são exigidos quando há banco de verdade,
    para os testes seguirem rodando offline com o InMemoryChunkRepository.
    """
    try:
        import psycopg
        from pgvector.psycopg import register_vector
    except ImportError as exc:  # pragma: no cover - caminho de produção
        raise ImportError(
            "Os pacotes 'psycopg[binary]' e 'pgvector' não estão instalados. "
            "Instale-os (requirements.txt) para falar com o Supabase."
        ) from exc
    from ..config import get_settings

    url = database_url or get_settings().database_url
    if not url:
        raise RuntimeError(
            "DATABASE_URL não configurada. Copie .env.example para .env e preencha "
            "com a connection string do Supabase (Project Settings → Database)."
        )
    conn = psycopg.connect(url)
    register_vector(conn)
    return conn
