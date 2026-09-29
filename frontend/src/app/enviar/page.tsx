"use client";

import { useRef, useState } from "react";
import { CheckCircle2, FileText, Info, Loader2, UploadCloud, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, TIPOS_DOCUMENTO, type UploadResultado } from "@/lib/api";
import { cn } from "@/lib/utils";

const LIMITE_MB = 50;

function tamanho(bytes: number) {
  return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`;
}

export default function PaginaEnviar() {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [orgao, setOrgao] = useState("");
  const [tipo, setTipo] = useState("atestado");
  const [arrastando, setArrastando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<UploadResultado | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const escolher = (f: File | undefined) => {
    setErro(null);
    setResultado(null);
    if (!f) return;
    if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
      setErro("Envie um arquivo PDF.");
      return;
    }
    if (f.size > LIMITE_MB * 1024 * 1024) {
      setErro(`O arquivo tem ${tamanho(f.size)}; o limite é ${LIMITE_MB} MB.`);
      return;
    }
    setArquivo(f);
  };

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!arquivo || orgao.trim().length < 2) return;
    setEnviando(true);
    setErro(null);
    try {
      setResultado(await api.upload(arquivo, orgao.trim(), tipo));
      setArquivo(null);
      setOrgao("");
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Falha no envio.");
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-14 shrink-0 items-center border-b bg-folha px-8">
        <h1 className="text-[15px] font-bold">Enviar documento</h1>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto grid max-w-[1100px] grid-cols-[1fr_320px] gap-10 px-8 py-8">
          <form onSubmit={enviar} className="flex flex-col gap-6">
            <div>
              <h2 className="text-[22px] font-bold tracking-tight">Novo documento para o acervo</h2>
              <p className="mt-1 text-sm text-grafite">
                Atestados, CATs, editais e atas em PDF, de até {LIMITE_MB} MB.
              </p>
            </div>

            <div
              onDragOver={(e) => {
                e.preventDefault();
                setArrastando(true);
              }}
              onDragLeave={() => setArrastando(false)}
              onDrop={(e) => {
                e.preventDefault();
                setArrastando(false);
                escolher(e.dataTransfer.files[0]);
              }}
              className={cn(
                "flex min-h-52 flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed bg-folha px-6 py-8 text-center transition-colors",
                arrastando ? "border-teal bg-teal-claro/50" : "border-input",
              )}
            >
              {arquivo ? (
                <div className="flex w-full max-w-md items-center gap-3 rounded-md border bg-folha px-4 py-3 text-left">
                  <FileText className="size-5 shrink-0 text-teal-texto" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{arquivo.name}</div>
                    <div className="tabular-nums text-xs text-grafite">{tamanho(arquivo.size)}</div>
                  </div>
                  <Button type="button" variant="ghost" size="icon-sm" aria-label="Remover arquivo" onClick={() => setArquivo(null)}>
                    <X />
                  </Button>
                </div>
              ) : (
                <>
                  <UploadCloud className="size-8 text-grafite" aria-hidden />
                  <div className="text-sm">
                    <span className="font-bold">Arraste o PDF para cá</span> ou
                  </div>
                  <Button type="button" variant="outline" size="sm" onClick={() => inputRef.current?.click()}>
                    Escolher arquivo
                  </Button>
                </>
              )}
              <input
                ref={inputRef}
                type="file"
                accept="application/pdf,.pdf"
                className="sr-only"
                onChange={(e) => escolher(e.target.files?.[0])}
              />
            </div>

            <div className="grid grid-cols-[1fr_220px] gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="orgao">Órgão contratante</Label>
                <Input
                  id="orgao"
                  value={orgao}
                  onChange={(e) => setOrgao(e.target.value)}
                  placeholder="Ex.: Instituto Butantan"
                  className="h-10 bg-folha"
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="tipo">Tipo de documento</Label>
                <Select value={tipo} onValueChange={setTipo}>
                  <SelectTrigger id="tipo" className="w-full bg-folha data-[size=default]:h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TIPOS_DOCUMENTO.map((t) => (
                      <SelectItem key={t.valor} value={t.valor}>
                        {t.rotulo}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {erro && <p className="text-sm text-destructive">{erro}</p>}

            {resultado && (
              <div className="flex items-start gap-3 rounded-md border border-teal/30 bg-teal-claro/60 px-4 py-3 text-sm">
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-teal-texto" />
                <div>
                  <div className="font-bold">{resultado.arquivo} recebido</div>
                  <p className="mt-0.5 text-grafite">{resultado.mensagem}</p>
                </div>
              </div>
            )}

            <div>
              <Button type="submit" className="h-10 px-5" disabled={!arquivo || orgao.trim().length < 2 || enviando}>
                {enviando ? <Loader2 className="animate-spin" /> : <UploadCloud />}
                Enviar documento
              </Button>
            </div>
          </form>

          <aside className="self-start rounded-lg border bg-folha p-5 text-sm leading-relaxed">
            <div className="mb-2 flex items-center gap-2 font-bold">
              <Info className="size-4 text-teal-texto" /> O que acontece depois do envio
            </div>
            <p className="text-grafite">
              A extração do texto e a indexação rodam em segundo plano e levam alguns minutos por documento —
              mais se o PDF for escaneado.
            </p>
            <p className="mt-3 text-grafite">
              O documento só aparece nas respostas depois que a situação dele no{" "}
              <span className="font-medium text-tinta">Acervo</span> mudar para{" "}
              <span className="font-medium text-tinta">Indexado</span>.
            </p>
            <p className="mt-3 text-grafite">
              Confira o órgão antes de enviar: é por ele que as respostas identificam o contratante.
            </p>
          </aside>
        </div>
      </div>
    </div>
  );
}
