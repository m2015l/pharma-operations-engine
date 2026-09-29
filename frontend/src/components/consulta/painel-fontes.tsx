"use client";

import { useEffect, useRef } from "react";
import { FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Citacao, Resposta } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AlvoFonte } from "@/components/visualizador-fonte";

/** O trecho vem do chunk cru: tira marcação markdown e linhas em branco em excesso. */
function limparTrecho(t: string) {
  return t.replace(/\*\*/g, "").replace(/^#+\s*/gm, "").replace(/\n\s*\n+/g, "\n").trim();
}

function paginas(c: Citacao) {
  return c.pagina_fim !== c.pagina_inicio ? `p. ${c.pagina_inicio}–${c.pagina_fim}` : `p. ${c.pagina_inicio}`;
}

type Props = {
  resposta: Resposta | null;
  indicePergunta: number | null;
  marcadorAtivo: number | null;
  onMarcador: (n: number) => void;
  onVerFonte: (alvo: AlvoFonte) => void;
};

export function PainelFontes({ resposta, indicePergunta, marcadorAtivo, onMarcador, onVerFonte }: Props) {
  const refs = useRef(new Map<number, HTMLElement>());

  useEffect(() => {
    if (marcadorAtivo == null) return;
    refs.current.get(marcadorAtivo)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [marcadorAtivo, resposta]);

  return (
    <aside aria-label="Fontes da resposta" className="flex w-[400px] shrink-0 flex-col border-l bg-folha">
      <div className="border-b px-5 py-4">
        <h2 className="text-sm font-semibold">Fontes</h2>
        <p className="mt-0.5 text-xs text-grafite">
          {resposta && indicePergunta != null
            ? `Trechos citados na resposta ${indicePergunta}`
            : "Os trechos citados aparecem aqui."}
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {!resposta && (
          <p className="px-1 text-sm leading-relaxed text-grafite">
            Cada afirmação da resposta traz um marcador numerado. Clique nele para ver de qual documento e
            página a informação saiu.
          </p>
        )}
        {resposta && resposta.citacoes.length === 0 && (
          <p className="px-1 text-sm leading-relaxed text-grafite">Esta resposta não cita nenhum trecho do acervo.</p>
        )}

        <ol className="flex flex-col gap-3">
          {resposta?.citacoes.map((c) => {
            const ativo = marcadorAtivo === c.marcador;
            return (
              <li
                key={c.marcador}
                ref={(el) => {
                  if (el) refs.current.set(c.marcador, el);
                  else refs.current.delete(c.marcador);
                }}
                className={cn(
                  "group rounded-md border bg-folha transition-[border-color,box-shadow]",
                  ativo ? "border-teal shadow-[0_0_0_3px_var(--teal-claro)]" : "hover:border-teal/40",
                )}
              >
                <button
                  type="button"
                  onClick={() => onMarcador(c.marcador)}
                  className="block w-full px-4 pt-3.5 pb-3 text-left"
                >
                  <div className="flex items-start gap-3">
                    <span
                      className={cn(
                        "mt-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-[3px] border px-1 tabular-nums text-[11px] font-semibold",
                        ativo ? "border-teal bg-teal-texto text-white" : "border-teal/45 bg-teal-claro text-teal-texto",
                      )}
                    >
                      {c.marcador}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-[11px] font-semibold tracking-[0.08em] text-grafite uppercase">
                        {c.orgao}
                      </div>
                      <div className="mt-0.5 text-sm leading-snug font-semibold">{c.titulo_documento}</div>
                      <div className="mt-1.5 tabular-nums text-[11px] leading-relaxed text-grafite">
                        <span className="font-semibold text-tinta">{paginas(c)}</span>
                        {c.secao ? ` · ${c.secao}` : " · folha de rosto (sem seção)"}
                      </div>
                    </div>
                  </div>
                  <blockquote className="mt-3 border-l-2 border-teal/35 pl-3 text-[13px] leading-relaxed whitespace-pre-line text-tinta/85">
                    {limparTrecho(c.trecho)}
                  </blockquote>
                </button>
                <div className="flex justify-end border-t border-dashed px-3 py-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-teal-texto hover:bg-teal-claro hover:text-teal-texto"
                    onClick={() =>
                      onVerFonte({
                        documentoId: c.documento_id,
                        titulo: c.titulo_documento,
                        pagina: c.pagina_inicio,
                        rotulo: `${c.orgao} · ${paginas(c)}${c.secao ? ` · ${c.secao}` : ""}`,
                      })
                    }
                  >
                    <FileText /> Ver a fonte
                  </Button>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </aside>
  );
}
