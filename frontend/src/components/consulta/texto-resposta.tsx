"use client";

import ReactMarkdown from "react-markdown";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Citacao } from "@/lib/api";
import { cn } from "@/lib/utils";

const PREFIXO = "#fonte-";

/** Troca [n] por um link markdown que o componente `a` abaixo vira marcador. */
function marcarCitacoes(texto: string) {
  return texto.replace(/\[(\d+)\]/g, (_, n) => `[${n}](${PREFIXO}${n})`);
}

type Props = {
  texto: string;
  citacoes: Citacao[];
  marcadorAtivo: number | null;
  onMarcador: (n: number) => void;
};

export function TextoResposta({ texto, citacoes, marcadorAtivo, onMarcador }: Props) {
  const porMarcador = new Map(citacoes.map((c) => [c.marcador, c]));

  return (
    <div className="resposta">
      <ReactMarkdown
        components={{
          a: ({ href, children }) => {
            if (!href?.startsWith(PREFIXO)) {
              return (
                <a href={href} className="underline" target="_blank" rel="noreferrer">
                  {children}
                </a>
              );
            }
            const n = Number(href.slice(PREFIXO.length));
            const c = porMarcador.get(n);
            if (!c) {
              // Marcador sem trecho correspondente = fonte inexistente (alucinação).
              return (
                <span
                  className="mx-0.5 rounded-sm bg-alerta-claro px-1 font-mono text-[0.72em] text-alerta line-through"
                  title="Fonte inexistente: o agente citou um trecho que não foi recuperado"
                >
                  {n}
                </span>
              );
            }
            return (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={() => onMarcador(n)}
                    aria-label={`Fonte ${n}: ${c.orgao}, página ${c.pagina_inicio}`}
                    className={cn(
                      "relative -top-[0.35em] mx-[0.08em] inline-flex h-[1.35em] min-w-[1.35em] items-center justify-center rounded-[3px] border px-[0.3em] align-baseline font-mono text-[0.62em] font-semibold leading-none transition-colors",
                      marcadorAtivo === n
                        ? "border-carimbo bg-carimbo text-white"
                        : "border-carimbo/45 bg-carimbo-claro text-carimbo hover:border-carimbo hover:bg-carimbo hover:text-white",
                    )}
                  >
                    {n}
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top" className="max-w-xs font-sans">
                  {c.orgao} · p.{c.pagina_inicio}
                  {c.pagina_fim !== c.pagina_inicio ? `–${c.pagina_fim}` : ""}
                </TooltipContent>
              </Tooltip>
            );
          },
        }}
      >
        {marcarCitacoes(texto)}
      </ReactMarkdown>
    </div>
  );
}
