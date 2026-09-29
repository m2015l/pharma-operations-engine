import type { Metadata } from "next";
import { Archivo, IBM_Plex_Mono, Source_Serif_4 } from "next/font/google";
import { BarraLateral } from "@/components/barra-lateral";
import { ConversaProvider } from "@/components/conversa-provider";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

// Archivo: interface e títulos. Source Serif 4: o texto das respostas, que é
// para ser lido como documento. IBM Plex Mono: páginas, CNPJ, marcadores.
const archivo = Archivo({ variable: "--font-archivo", subsets: ["latin"] });
const sourceSerif = Source_Serif_4({ variable: "--font-source-serif", subsets: ["latin"] });
const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Solufarma · Acervo técnico",
  description: "Consulta ao acervo técnico de licitações da Solufarma Engenharia",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="pt-BR"
      className={`${archivo.variable} ${sourceSerif.variable} ${plexMono.variable} h-full antialiased`}
    >
      <body className="h-full">
        <TooltipProvider delayDuration={200}>
          <ConversaProvider>
            <div className="flex h-dvh min-w-[1024px] overflow-hidden">
              <BarraLateral />
              <main className="flex min-w-0 flex-1 flex-col">{children}</main>
            </div>
          </ConversaProvider>
        </TooltipProvider>
        <Toaster position="bottom-right" />
      </body>
    </html>
  );
}
