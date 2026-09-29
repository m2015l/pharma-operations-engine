import type { Resposta } from "@/lib/api";

/**
 * "N citadas de M trechos recuperados" (I10, PRECISÃO.md), com uma régua de M
 * traços em que os N citados ficam em teal. Mostra de relance quanto
 * do que a busca trouxe o agente realmente usou — e explica os "buracos" na
 * numeração ([1][2][4] sem [3]) sem parecer bug.
 */
export function SeloRastreio({ resposta }: { resposta: Resposta }) {
  const { citacoes, trechos_recuperados: total } = resposta;
  const citados = new Set(citacoes.map((c) => c.marcador));
  const tracos = Array.from({ length: Math.max(total, citados.size) }, (_, i) => i + 1);

  return (
    <div className="flex items-center gap-3 text-xs text-grafite">
      <div className="flex items-end gap-[3px]" aria-hidden>
        {tracos.map((n) => (
          <span
            key={n}
            className={
              citados.has(n) ? "h-3 w-[5px] rounded-[1px] bg-teal-texto" : "h-2 w-[5px] rounded-[1px] bg-linha"
            }
          />
        ))}
      </div>
      <span>
        <span className="tabular-nums font-semibold text-tinta">{citacoes.length}</span>{" "}
        {citacoes.length === 1 ? "citada" : "citadas"} de{" "}
        <span className="tabular-nums font-semibold text-tinta">{total}</span>{" "}
        {total === 1 ? "trecho recuperado" : "trechos recuperados"}
      </span>
    </div>
  );
}
