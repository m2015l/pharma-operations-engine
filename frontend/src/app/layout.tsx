import type { Metadata } from "next";
import { Lato } from "next/font/google";
import { ConversaProvider } from "@/components/conversa-provider";
import { Cabecalho } from "@/components/moldura/cabecalho";
import { Rodape } from "@/components/moldura/rodape";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

// Lato: a fonte do tema Flatly, que o sistema Contratos usa. Não é variável,
// então os pesos são obrigatórios (300 no título grande, 400 texto, 700 destaque).
const lato = Lato({ variable: "--font-lato", subsets: ["latin"], weight: ["300", "400", "700"] });

export const metadata: Metadata = {
  title: "Solufarma · Acervo técnico",
  description: "Consulta ao acervo técnico de licitações da Solufarma Engenharia",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="pt-BR"
      className={`${lato.variable} h-full antialiased`}
    >
      <body className="h-full">
        <TooltipProvider delayDuration={200}>
          <ConversaProvider>
            <div className="flex h-dvh min-w-[1024px] flex-col overflow-hidden">
              <Cabecalho />
              <main className="flex min-h-0 flex-1 flex-col">{children}</main>
              <Rodape />
            </div>
          </ConversaProvider>
        </TooltipProvider>
        <Toaster position="bottom-right" />
      </body>
    </html>
  );
}
