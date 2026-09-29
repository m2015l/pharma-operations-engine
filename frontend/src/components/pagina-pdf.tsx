"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { PDFDocumentProxy } from "pdfjs-dist";

/**
 * Renderiza UMA página do PDF com pdf.js, abrindo direto na página citada.
 * Não depende do visualizador de PDF do navegador (que varia, e não existe em
 * navegador headless) e funciona igual para a URL assinada do Storage e para
 * o arquivo local do modo demo. O worker é copiado para /public no postinstall.
 */
export function PaginaPdf({ url, paginaInicial }: { url: string; paginaInicial: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const caixaRef = useRef<HTMLDivElement>(null);
  const [doc, setDoc] = useState<{ url: string; pdf: PDFDocumentProxy } | null>(null);
  const [pagina, setPagina] = useState({ url, n: paginaInicial });
  const [erro, setErro] = useState<{ url: string; msg: string } | null>(null);
  const [renderizada, setRenderizada] = useState<string | null>(null);

  // Troca de URL/página inicial: o estado derivado se ajusta sem efeito.
  const n = pagina.url === url ? pagina.n : paginaInicial;
  const pdf = doc?.url === url ? doc.pdf : null;
  const msgErro = erro?.url === url ? erro.msg : null;

  useEffect(() => {
    let vivo = true;
    let tarefa: { destroy: () => Promise<void> } | null = null;
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
        const t = pdfjs.getDocument({ url });
        tarefa = t;
        const carregado = await t.promise;
        if (vivo) setDoc({ url, pdf: carregado });
      } catch (e) {
        if (vivo) setErro({ url, msg: e instanceof Error ? e.message : "Falha ao ler o PDF" });
      }
    })();
    return () => {
      vivo = false;
      tarefa?.destroy();
    };
  }, [url]);

  useEffect(() => {
    if (!pdf || !canvasRef.current || !caixaRef.current) return;
    let cancelado = false;
    const alvo = Math.min(Math.max(1, n), pdf.numPages);
    let render: { cancel: () => void; promise: Promise<void> } | null = null;
    (async () => {
      const pag = await pdf.getPage(alvo);
      if (cancelado || !canvasRef.current || !caixaRef.current) return;
      const largura = caixaRef.current.clientWidth - 32;
      const base = pag.getViewport({ scale: 1 });
      const escala = Math.min(largura / base.width, 2);
      const dpr = window.devicePixelRatio || 1;
      const vp = pag.getViewport({ scale: escala * dpr });
      const canvas = canvasRef.current;
      canvas.width = vp.width;
      canvas.height = vp.height;
      canvas.style.width = `${vp.width / dpr}px`;
      canvas.style.height = `${vp.height / dpr}px`;
      render = pag.render({ canvas, viewport: vp });
      try {
        await render.promise;
        if (!cancelado) setRenderizada(`${url}#${alvo}`);
      } catch {
        /* render cancelado ao trocar de página */
      }
    })();
    return () => {
      cancelado = true;
      render?.cancel();
    };
  }, [pdf, n, url]);

  const total = pdf?.numPages ?? 0;
  const atual = total ? Math.min(Math.max(1, n), total) : n;
  const pronta = renderizada === `${url}#${atual}`;
  const irPara = (novo: number) => setPagina({ url, n: Math.min(Math.max(1, novo), total) });

  return (
    <div className="flex h-full flex-col">
      <div ref={caixaRef} className="relative min-h-0 flex-1 overflow-auto bg-[#5f6b76]/15 p-4">
        {msgErro ? (
          <div className="flex h-full items-center justify-center text-sm text-destructive">{msgErro}</div>
        ) : (
          <>
            {!pronta && (
              <div className="absolute inset-0 flex items-center justify-center gap-2 text-sm text-grafite">
                <Loader2 className="size-4 animate-spin" /> Abrindo a página {atual}…
              </div>
            )}
            <canvas
              ref={canvasRef}
              className={`mx-auto block bg-white shadow-[0_2px_12px_rgba(21,32,43,0.18)] transition-opacity ${pronta ? "opacity-100" : "opacity-0"}`}
            />
          </>
        )}
      </div>
      {total > 0 && (
        <div className="flex items-center justify-center gap-3 border-t bg-folha py-2">
          <Button variant="ghost" size="icon-sm" onClick={() => irPara(atual - 1)} disabled={atual <= 1} aria-label="Página anterior">
            <ChevronLeft />
          </Button>
          <span className="font-mono text-xs text-grafite">
            página <span className="font-semibold text-tinta">{atual}</span> de {total}
          </span>
          <Button variant="ghost" size="icon-sm" onClick={() => irPara(atual + 1)} disabled={atual >= total} aria-label="Próxima página">
            <ChevronRight />
          </Button>
        </div>
      )}
    </div>
  );
}
