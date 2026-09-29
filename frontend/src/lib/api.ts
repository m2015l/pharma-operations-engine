// Contratos da API Python (api/schemas.py). O navegador só chama /api/*,
// que o Next repassa para a API — ver next.config.ts.

export type Citacao = {
  marcador: number;
  chunk_chave: string;
  documento_id: string;
  titulo_documento: string;
  tipo_documento: string;
  orgao: string;
  secao: string;
  pagina_inicio: number;
  pagina_fim: number;
  trecho: string;
};

export type Resposta = {
  texto: string;
  citacoes: Citacao[];
  trechos_recuperados: number;
  contrato_citacao_ok: boolean;
  citacoes_invalidas: number[];
  encontrou_no_acervo: boolean;
  tipo_fluxo: string;
  modo: "demo" | "real";
  origem: string | null;
};

export type Documento = {
  id: string;
  titulo: string;
  tipo: string;
  orgao: string;
  num_paginas: number | null;
  num_chunks: number;
  status: string;
  indexado_em: string | null;
};

export type Fonte = {
  documento_id: string;
  titulo: string;
  url: string | null;
  expira_em_segundos: number | null;
  disponivel: boolean;
  motivo: string | null;
};

export type Saude = { modo: "demo" | "real"; documentos: number };

export type UploadResultado = {
  status: string;
  arquivo: string;
  tamanho_bytes: number;
  orgao: string;
  tipo: string;
  mensagem: string;
  /** Só no modo real: acompanhar em GET /uploads/{id}. */
  envio_id: string | null;
};

export type EtapaEnvio = {
  chave: string;
  rotulo: string;
  estado: "pendente" | "andamento" | "ok" | "erro";
  detalhe: string | null;
};

export type Envio = {
  id: string;
  arquivo: string;
  orgao: string;
  tipo: string;
  criado_em: string;
  estado: "na_fila" | "processando" | "concluido" | "erro";
  etapas: EtapaEnvio[];
  titulo: string | null;
  documento_id: string | null;
  erro: string | null;
};

export const TIPOS_DOCUMENTO = [
  { valor: "atestado", rotulo: "Atestado / CAT" },
  { valor: "edital", rotulo: "Edital" },
  { valor: "ata", rotulo: "Ata" },
  { valor: "resultado", rotulo: "Resultado" },
  { valor: "anexo", rotulo: "Anexo" },
  { valor: "proposta", rotulo: "Proposta" },
  { valor: "recurso", rotulo: "Recurso" },
  { valor: "outro", rotulo: "Outro" },
] as const;

export function rotuloTipo(tipo: string) {
  return TIPOS_DOCUMENTO.find((t) => t.valor === tipo)?.rotulo ?? tipo;
}

async function lerErro(r: Response): Promise<string> {
  try {
    const corpo = await r.json();
    if (typeof corpo?.detail === "string") return corpo.detail;
  } catch {}
  if (r.status >= 500) return "A API não respondeu. Confira se ela está rodando na porta 8000.";
  return `Erro ${r.status}`;
}

async function pedir<T>(caminho: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`/api${caminho}`, init);
  } catch {
    throw new Error("Sem conexão com a API. Confira se ela está rodando na porta 8000.");
  }
  if (!r.ok) throw new Error(await lerErro(r));
  return r.json() as Promise<T>;
}

export type TurnoHistorico = { pergunta: string; resposta: string };

export type TurnoExportado = {
  pergunta: string;
  perguntado_em: string | null;
  resposta: Resposta | null;
  erro: string | null;
};

export type ExportarDocxCorpo = {
  escopo: "conversa" | "resposta";
  gerado_em: string;
  turnos: TurnoExportado[];
};

/** Nome sugerido pela API em `Content-Disposition: attachment; filename="..."`. */
function nomeDoArquivo(r: Response, padrao: string) {
  const m = r.headers.get("Content-Disposition")?.match(/filename="?([^";]+)"?/i);
  return m?.[1] ?? padrao;
}

export const api = {
  saude: () => pedir<Saude>("/saude"),
  sugestoes: () => pedir<string[]>("/sugestoes"),
  documentos: () => pedir<Documento[]>("/documentos"),
  fonte: (id: string) => pedir<Fonte>(`/documentos/${id}/fonte`),
  perguntar: (pergunta: string, historico: TurnoHistorico[]) =>
    pedir<Resposta>("/perguntar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pergunta, historico }),
    }),
  /** POST /exportar/docx: a API só formata o que já está na tela (custo zero). */
  exportarDocx: async (corpo: ExportarDocxCorpo): Promise<{ blob: Blob; nome: string }> => {
    let r: Response;
    try {
      r = await fetch("/api/exportar/docx", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corpo),
      });
    } catch {
      throw new Error("Sem conexão com a API. Confira se ela está rodando na porta 8000.");
    }
    if (!r.ok) throw new Error(await lerErro(r));
    return { blob: await r.blob(), nome: nomeDoArquivo(r, `${corpo.escopo}-solufarma.docx`) };
  },
  envios: () => pedir<Envio[]>("/uploads"),
  envio: (id: string) => pedir<Envio>(`/uploads/${id}`),
  upload: (arquivo: File, orgao: string, tipo: string) => {
    const form = new FormData();
    form.append("arquivo", arquivo);
    form.append("orgao", orgao);
    form.append("tipo", tipo);
    return pedir<UploadResultado>("/upload", { method: "POST", body: form });
  },
};
