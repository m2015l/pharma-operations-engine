"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FileUp, Library, MessageSquareText } from "lucide-react";
import { cn } from "@/lib/utils";
import { useConversa } from "@/components/conversa-provider";

const ITENS = [
  { href: "/", rotulo: "Consulta", icone: MessageSquareText },
  { href: "/acervo", rotulo: "Acervo", icone: Library },
  { href: "/enviar", rotulo: "Enviar documento", icone: FileUp },
];

export function BarraLateral() {
  const caminho = usePathname();
  const { saude } = useConversa();

  return (
    <aside className="flex w-60 shrink-0 flex-col bg-tinta text-white/90">
      <div className="px-5 pt-6 pb-8">
        <div className="text-[0.95rem] font-bold tracking-[0.18em] text-white">SOLUFARMA</div>
        <div className="mt-1 text-xs text-white/55">Acervo técnico de licitações</div>
      </div>

      <nav aria-label="Principal" className="flex flex-col gap-0.5 px-3">
        {ITENS.map(({ href, rotulo, icone: Icone }) => {
          const ativo = href === "/" ? caminho === "/" : caminho.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={ativo ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                ativo ? "bg-white/12 font-semibold text-white" : "text-white/70 hover:bg-white/6 hover:text-white",
              )}
            >
              <Icone className="size-4" aria-hidden />
              {rotulo}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto px-5 pb-6">
        {saude?.modo === "demo" && (
          <div className="rounded-md border border-white/15 px-3 py-2.5 text-xs leading-relaxed text-white/70">
            <div className="mb-0.5 font-semibold text-white">Modo demonstração</div>
            Respostas gravadas das auditorias do agente. Nenhuma consulta é cobrada.
          </div>
        )}
        {saude?.modo === "real" && (
          <div className="text-xs text-white/55">
            Conectado ao acervo · {saude.documentos} documentos
          </div>
        )}
        {saude === null && (
          <div className="text-xs text-white/55">Sem conexão com a API</div>
        )}
      </div>
    </aside>
  );
}
