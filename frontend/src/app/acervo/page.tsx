"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, FileText, FileUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { VisualizadorFonte, type AlvoFonte } from "@/components/visualizador-fonte";
import { api, rotuloTipo, type Documento } from "@/lib/api";

const STATUS: Record<string, string> = {
  indexado: "Indexado",
  pendente: "Na fila",
  extraido: "Texto extraído",
  chunked: "Dividido em trechos",
  erro: "Erro no processamento",
};

function formatarData(iso: string | null) {
  if (!iso) return "—";
  const [a, m, d] = iso.split("-");
  return `${d}/${m}/${a}`;
}

export default function PaginaAcervo() {
  const [docs, setDocs] = useState<Documento[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [alvo, setAlvo] = useState<AlvoFonte | null>(null);

  useEffect(() => {
    api.documentos().then(setDocs).catch((e: Error) => setErro(e.message));
  }, []);

  const totalTrechos = docs?.reduce((s, d) => s + d.num_chunks, 0) ?? 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-14 shrink-0 items-center justify-between border-b bg-folha px-8">
        <h1 className="text-[15px] font-bold">Acervo</h1>
        <Button variant="outline" size="sm" asChild>
          <Link href="/enviar">
            <FileUp /> Enviar documento
          </Link>
        </Button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1100px] px-8 py-8">
          <div className="mb-6">
            <h2 className="text-[22px] font-bold tracking-tight">Documentos indexados</h2>
            <p className="mt-1 text-sm text-grafite">
              {docs
                ? `${docs.length} ${docs.length === 1 ? "documento" : "documentos"} · ${totalTrechos.toLocaleString("pt-BR")} trechos pesquisáveis. Só o que está aqui entra nas respostas.`
                : "Carregando…"}
            </p>
          </div>

          {erro && (
            <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              <AlertTriangle className="mt-0.5 size-4" /> {erro}
            </div>
          )}

          {!erro && (
            <div className="overflow-hidden rounded-lg border bg-folha">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/60 hover:bg-muted/60">
                    <TableHead className="w-[44%] pl-5">Documento</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead className="text-right">Páginas</TableHead>
                    <TableHead className="text-right">Trechos</TableHead>
                    <TableHead>Indexado em</TableHead>
                    <TableHead>Situação</TableHead>
                    <TableHead className="pr-5" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {!docs &&
                    Array.from({ length: 4 }, (_, i) => (
                      <TableRow key={i}>
                        <TableCell colSpan={7} className="px-5 py-4">
                          <Skeleton className="h-5 w-2/3" />
                        </TableCell>
                      </TableRow>
                    ))}
                  {docs?.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={7} className="px-5 py-10 text-center text-sm text-grafite">
                        Nenhum documento indexado ainda. Envie o primeiro atestado para começar.
                      </TableCell>
                    </TableRow>
                  )}
                  {docs?.map((d) => (
                    <TableRow key={d.id}>
                      <TableCell className="py-3.5 pl-5 whitespace-normal">
                        <div className="text-[11px] font-bold tracking-[0.08em] text-grafite uppercase">
                          {d.orgao}
                        </div>
                        <div className="mt-0.5 font-medium">{d.titulo}</div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{rotuloTipo(d.tipo)}</Badge>
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-[13px]">{d.num_paginas ?? "—"}</TableCell>
                      <TableCell className="text-right tabular-nums text-[13px]">{d.num_chunks}</TableCell>
                      <TableCell className="tabular-nums text-[13px]">{formatarData(d.indexado_em)}</TableCell>
                      <TableCell>
                        <span className="inline-flex items-center gap-1.5 text-[13px]">
                          <span
                            className={`size-1.5 rounded-full ${d.status === "indexado" ? "bg-teal-texto" : d.status === "erro" ? "bg-destructive" : "bg-alerta"}`}
                          />
                          {STATUS[d.status] ?? d.status}
                        </span>
                      </TableCell>
                      <TableCell className="pr-5 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-teal-texto hover:bg-teal-claro hover:text-teal-texto"
                          onClick={() => setAlvo({ documentoId: d.id, titulo: d.titulo, pagina: 1 })}
                        >
                          <FileText /> Abrir PDF
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </div>

      <VisualizadorFonte alvo={alvo} onFechar={() => setAlvo(null)} />
    </div>
  );
}
