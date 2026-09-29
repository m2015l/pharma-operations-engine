"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, FileText, FileUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CabecalhoPagina } from "@/components/moldura/cabecalho-pagina";
import { VisualizadorFonte, type AlvoFonte } from "@/components/visualizador-fonte";
import { api, rotuloTipo, type Documento } from "@/lib/api";
import { cn } from "@/lib/utils";

type Situacao = "indexado" | "processando" | "erro";

// status_processamento do banco → as três situações da legenda.
function situacao(status: string): Situacao {
  if (status === "indexado") return "indexado";
  if (status === "erro") return "erro";
  return "processando";
}

const SITUACAO: Record<Situacao, { rotulo: string; badge: string; ponto: string }> = {
  indexado: { rotulo: "Indexado", badge: "bg-teal-texto text-white", ponto: "bg-teal-texto" },
  processando: { rotulo: "Em processamento", badge: "bg-alerta-claro text-alerta", ponto: "bg-alerta" },
  erro: { rotulo: "Erro", badge: "bg-erro-claro text-erro", ponto: "bg-erro" },
};

const TODOS = "todos";

function formatarData(iso: string | null) {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

/** Sem acento e minúsculo, para a busca achar "fundacao" em "Fundação". */
function dobrar(texto: string) {
  return texto.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

export default function PaginaAcervo() {
  const [docs, setDocs] = useState<Documento[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [alvo, setAlvo] = useState<AlvoFonte | null>(null);
  const [busca, setBusca] = useState("");
  const [tipo, setTipo] = useState(TODOS);

  useEffect(() => {
    api.documentos().then(setDocs).catch((e: Error) => setErro(e.message));
  }, []);

  const totalTrechos = docs?.reduce((s, d) => s + d.num_chunks, 0) ?? 0;
  // Acervo pequeno: filtrar no cliente a cada render custa nada.
  const tipos = [...new Set(docs?.map((d) => d.tipo) ?? [])].sort();
  const termo = dobrar(busca.trim());
  const filtrados = (docs ?? []).filter(
    (d) =>
      (tipo === TODOS || d.tipo === tipo) &&
      (!termo || dobrar(d.titulo).includes(termo) || dobrar(d.orgao).includes(termo)),
  );

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[1480px] px-8 pt-7 pb-8 xl:px-12">
        <CabecalhoPagina
          titulo="Acervo"
          subtitulo={
            docs
              ? `${docs.length} ${docs.length === 1 ? "documento" : "documentos"} · ${totalTrechos.toLocaleString("pt-BR")} trechos pesquisáveis. Atestados de capacidade técnica e CATs: só o que está aqui entra nas respostas.`
              : "Carregando…"
          }
          acoes={
            <Button variant="outline" asChild className="h-9 px-3.5">
              <Link href="/enviar">
                <FileUp /> Enviar documento
              </Link>
            </Button>
          }
        />

        <div className="mb-4 flex items-center gap-4 text-sm text-grafite">
          {(Object.keys(SITUACAO) as Situacao[]).map((s) => (
            <span key={s} className="inline-flex items-center gap-1.5">
              <span className={cn("size-2.5 rounded-full", SITUACAO[s].ponto)} aria-hidden />
              {SITUACAO[s].rotulo}
            </span>
          ))}
        </div>

        {erro && (
          <div className="flex items-start gap-2 rounded-md bg-erro-claro px-4 py-3 text-sm text-erro">
            <AlertTriangle className="mt-0.5 size-4" /> {erro}
          </div>
        )}

        {!erro && (
          <section className="overflow-hidden rounded-md bg-folha shadow-card">
            <div className="flex items-end gap-4 border-b px-5 py-4">
              <div className="flex max-w-md flex-1 flex-col gap-1.5">
                <Label htmlFor="busca">Buscar</Label>
                <Input
                  id="busca"
                  value={busca}
                  onChange={(e) => setBusca(e.target.value)}
                  placeholder="Título ou órgão…"
                  className="h-9 bg-folha"
                />
              </div>
              <div className="flex w-56 flex-col gap-1.5">
                <Label htmlFor="filtro-tipo">Tipo</Label>
                <Select value={tipo} onValueChange={setTipo}>
                  <SelectTrigger id="filtro-tipo" className="w-full bg-folha data-[size=default]:h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={TODOS}>Todos</SelectItem>
                    {tipos.map((t) => (
                      <SelectItem key={t} value={t}>
                        {rotuloTipo(t)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <p className="ml-auto pb-2 text-sm text-grafite tabular-nums">
                {docs && (busca || tipo !== TODOS) ? `${filtrados.length} de ${docs.length}` : ""}
              </p>
            </div>

            <h2 className="px-5 pt-4 pb-1 text-base font-bold">Documentos indexados</h2>
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="w-[44%] pl-5 font-bold">Documento</TableHead>
                  <TableHead className="font-bold">Tipo</TableHead>
                  <TableHead className="text-right font-bold">Páginas</TableHead>
                  <TableHead className="text-right font-bold">Trechos</TableHead>
                  <TableHead className="font-bold">Indexado em</TableHead>
                  <TableHead className="font-bold">Situação</TableHead>
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
                      Nenhum documento no acervo ainda. Envie o primeiro atestado para começar.
                    </TableCell>
                  </TableRow>
                )}
                {docs && docs.length > 0 && filtrados.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} className="px-5 py-10 text-center text-sm text-grafite">
                      Nenhum documento com esse filtro.
                    </TableCell>
                  </TableRow>
                )}
                {filtrados.map((d) => {
                  const s = SITUACAO[situacao(d.status)];
                  return (
                    <TableRow key={d.id}>
                      <TableCell className="py-3.5 pl-5 whitespace-normal">
                        <div className="text-[11px] font-bold tracking-[0.08em] text-grafite uppercase">
                          {d.orgao}
                        </div>
                        <div className="mt-0.5">{d.titulo}</div>
                      </TableCell>
                      <TableCell>
                        <span className="rounded-full border px-2 py-0.5 text-xs">{rotuloTipo(d.tipo)}</span>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{d.num_paginas ?? "—"}</TableCell>
                      <TableCell className="text-right tabular-nums">{d.num_chunks}</TableCell>
                      <TableCell className="tabular-nums">{formatarData(d.indexado_em)}</TableCell>
                      <TableCell>
                        <span
                          className={cn("rounded-full px-2.5 py-0.5 text-xs font-bold", s.badge)}
                          title={d.status}
                        >
                          {s.rotulo}
                        </span>
                      </TableCell>
                      <TableCell className="pr-5 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="font-bold text-teal-texto hover:bg-teal-claro hover:text-teal-texto hover:underline"
                          onClick={() => setAlvo({ documentoId: d.id, titulo: d.titulo, pagina: 1 })}
                        >
                          <FileText /> Abrir PDF
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </section>
        )}
      </div>

      <VisualizadorFonte alvo={alvo} onFechar={() => setAlvo(null)} />
    </div>
  );
}
