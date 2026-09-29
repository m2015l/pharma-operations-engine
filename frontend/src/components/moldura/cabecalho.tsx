"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useConversa } from "@/components/conversa-provider";
import { Logo } from "@/components/moldura/logo";
import { cn } from "@/lib/utils";

// Os nomes precisam continuar "Consulta", "Acervo" e "Enviar documento":
// o frontend/demo/gravar_demo.py navega por eles (role=link).
const ITENS = [
  { href: "/", rotulo: "Consulta" },
  { href: "/acervo", rotulo: "Acervo" },
  { href: "/enviar", rotulo: "Enviar documento" },
];

/**
 * Header no padrão do sistema Contratos: branco, logo | nome do módulo à
 * esquerda, navegação em botões outline à direita (o ativo preenchido em
 * verde-petróleo) e borda inferior de 2 px #124443.
 */
export function Cabecalho() {
  const caminho = usePathname();

  return (
    <header className="shrink-0 border-b-2 border-petroleo bg-folha">
      <div className="mx-auto flex h-[60px] max-w-[1480px] items-center gap-4 px-8 xl:px-12">
        <Link href="/" className="flex items-center rounded-sm" aria-label="Início: Consulta">
          <Logo />
        </Link>
        <span className="h-7 w-px bg-linha" aria-hidden />
        <span className="text-lg font-bold text-petroleo">Licitações</span>
        <SeloModo />

        <nav aria-label="Principal" className="ml-auto flex items-center gap-2">
          {ITENS.map(({ href, rotulo }) => {
            const ativo = href === "/" ? caminho === "/" : caminho.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={ativo ? "page" : undefined}
                className={cn(
                  "inline-flex h-8 items-center rounded-[4px] border px-3 text-sm transition-colors",
                  ativo
                    ? "border-petroleo bg-petroleo text-white"
                    : "border-tinta/70 bg-folha text-tinta hover:bg-fundo",
                )}
              >
                {rotulo}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}

function SeloModo() {
  const { saude } = useConversa();
  if (saude === undefined || saude?.modo === "real") return null;

  if (saude === null) {
    return (
      <span className="rounded-full bg-erro-claro px-2.5 py-0.5 text-xs font-bold text-erro">
        Sem conexão com a API
      </span>
    );
  }
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          className="cursor-default rounded-full bg-alerta-claro px-2.5 py-0.5 text-xs font-bold text-alerta"
        >
          Demonstração
        </span>
      </TooltipTrigger>
      <TooltipContent side="bottom">
        Respostas gravadas das auditorias. Nenhuma consulta é cobrada.
      </TooltipContent>
    </Tooltip>
  );
}
