"use client";

import { useEffect, useState } from "react";
import { ExternalLink, FileWarning, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PaginaPdf } from "@/components/pagina-pdf";
import { api, type Fonte } from "@/lib/api";

export type AlvoFonte = { documentoId: string; titulo: string; pagina: number; rotulo?: string };

type Estado =
  | { tipo: "carregando" }
  | { tipo: "pronto"; fonte: Fonte }
  | { tipo: "erro"; mensagem: string };

/**
 * Abre o PDF original na página citada. A URL vem da API: assinada (10 min)
 * no modo real, arquivo local no modo demo. Nenhuma chave passa por aqui.
 */
export function VisualizadorFonte({ alvo, onFechar }: { alvo: AlvoFonte | null; onFechar: () => void }) {
  // O estado guarda de qual documento é: se o alvo mudou e a resposta ainda
  // não chegou, o que está guardado é de outro documento → "carregando".
  const [resultado, setResultado] = useState<{ id: string; estado: Estado } | null>(null);
  const estado: Estado =
    alvo && resultado?.id === alvo.documentoId ? resultado.estado : { tipo: "carregando" };

  useEffect(() => {
    if (!alvo) return;
    let vivo = true;
    const id = alvo.documentoId;
    api
      .fonte(id)
      .then((fonte) => vivo && setResultado({ id, estado: { tipo: "pronto", fonte } }))
      .catch((e: Error) => vivo && setResultado({ id, estado: { tipo: "erro", mensagem: e.message } }));
    return () => {
      vivo = false;
    };
  }, [alvo]);

  const url = estado.tipo === "pronto" ? estado.fonte.url : null;

  return (
    <Dialog open={alvo !== null} onOpenChange={(aberto) => !aberto && onFechar()}>
      <DialogContent className="flex h-[90vh] w-[min(1100px,92vw)] max-w-none flex-col gap-3 p-5 sm:max-w-none">
        <DialogHeader className="pr-8">
          <DialogTitle className="text-base">{alvo?.titulo}</DialogTitle>
          <DialogDescription className="tabular-nums text-xs">
            {alvo?.rotulo ?? `Página ${alvo?.pagina}`}
            {estado.tipo === "pronto" && estado.fonte.expira_em_segundos
              ? ` · link válido por ${Math.round(estado.fonte.expira_em_segundos / 60)} min`
              : ""}
          </DialogDescription>
        </DialogHeader>

        <div className="relative min-h-0 flex-1 overflow-hidden rounded-md border bg-muted">
          {estado.tipo === "carregando" && (
            <div className="flex h-full items-center justify-center gap-2 text-sm text-grafite">
              <Loader2 className="size-4 animate-spin" /> Gerando o link do documento…
            </div>
          )}
          {estado.tipo === "erro" && (
            <MensagemSemPdf titulo="Não foi possível abrir o PDF" texto={estado.mensagem} />
          )}
          {estado.tipo === "pronto" && !estado.fonte.disponivel && (
            <MensagemSemPdf
              titulo="PDF indisponível nesta versão"
              texto={estado.fonte.motivo ?? "O arquivo original não está acessível."}
            />
          )}
          {url && alvo && <PaginaPdf url={url} paginaInicial={alvo.pagina} />}
        </div>

        {url && (
          <div className="flex justify-end">
            <Button variant="outline" size="sm" asChild>
              <a href={`${url}#page=${alvo?.pagina ?? 1}`} target="_blank" rel="noreferrer">
                <ExternalLink /> Abrir em nova aba
              </a>
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function MensagemSemPdf({ titulo, texto }: { titulo: string; texto: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-10 text-center">
      <FileWarning className="size-6 text-grafite" />
      <div className="font-bold">{titulo}</div>
      <p className="max-w-md text-sm text-grafite">{texto}</p>
    </div>
  );
}
