"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, CheckCircle2, FileText, Info, Loader2, UploadCloud, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CabecalhoPagina } from "@/components/moldura/cabecalho-pagina";
import { useConversa } from "@/components/conversa-provider";
import { ProgressoEnvio } from "@/components/enviar/progresso-envio";
import { api, type Envio, type UploadResultado } from "@/lib/api";
import { cn } from "@/lib/utils";

const LIMITE_MB = 50;
// O acervo é só de resultado final: atestados de capacidade técnica e CATs.
// Editais e atas não entram.
const TIPO = "atestado";
// Intervalo de consulta ao progresso enquanto houver envio em andamento.
const POLL_MS = 2000;

function tamanho(bytes: number) {
  return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`;
}

export default function PaginaEnviar() {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [orgao, setOrgao] = useState("");
  const [arrastando, setArrastando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<UploadResultado | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { saude } = useConversa();
  const demo = saude?.modo === "demo";
  const [envios, setEnvios] = useState<Envio[]>([]);

  const atualizarEnvios = useCallback(() => {
    api.envios().then(setEnvios).catch(() => {});
  }, []);

  useEffect(() => {
    if (saude?.modo === "real") atualizarEnvios();
  }, [saude, atualizarEnvios]);

  const aprovar = useCallback(
    (id: string) => {
      api.aprovarEnvio(id).then(atualizarEnvios).catch((err: Error) => setErro(err.message));
    },
    [atualizarEnvios],
  );

  const emAndamento = envios.some((e) => e.estado === "na_fila" || e.estado === "processando");
  useEffect(() => {
    if (!emAndamento) return;
    const id = setInterval(atualizarEnvios, POLL_MS);
    return () => clearInterval(id);
  }, [emAndamento, atualizarEnvios]);

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
      const r = await api.upload(arquivo, orgao.trim(), TIPO);
      setResultado(r);
      if (r.envio_id) atualizarEnvios();
      setArquivo(null);
      setOrgao("");
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Falha no envio.");
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[1480px] px-8 pt-5 pb-8 xl:px-12">
        <CabecalhoPagina
          antes={
            <Link
              href="/acervo"
              className="mb-2 inline-flex items-center gap-1 text-sm text-petroleo underline underline-offset-2 hover:text-petroleo-hover"
            >
              <ArrowLeft className="size-3.5" /> Acervo
            </Link>
          }
          titulo="Enviar documento"
          subtitulo={`Atestados de capacidade técnica e CATs em PDF, de até ${LIMITE_MB} MB.`}
        />

        <div className="grid grid-cols-[minmax(0,1fr)_340px] items-start gap-5">
          <form onSubmit={enviar} className="flex flex-col gap-5 rounded-md bg-folha p-6 shadow-card">
            <h2 className="text-lg font-bold">Novo documento para o acervo</h2>

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
                "flex min-h-48 flex-col items-center justify-center gap-3 rounded-md border-2 border-dashed px-6 py-8 text-center transition-colors",
                arrastando ? "border-teal bg-teal-claro" : "border-linha",
              )}
            >
              {arquivo ? (
                <div className="flex w-full max-w-md items-center gap-3 rounded-md border bg-folha px-4 py-3 text-left">
                  <FileText className="size-5 shrink-0 text-teal-texto" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-bold">{arquivo.name}</div>
                    <div className="text-xs text-grafite tabular-nums">{tamanho(arquivo.size)}</div>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Remover arquivo"
                    onClick={() => {
                      setArquivo(null);
                      if (inputRef.current) inputRef.current.value = "";
                    }}
                  >
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

            <div className="flex flex-col gap-2">
              <Label htmlFor="orgao">Órgão contratante</Label>
              <Input
                id="orgao"
                value={orgao}
                onChange={(e) => setOrgao(e.target.value)}
                placeholder="Ex.: Instituto BioPharma"
                className="h-10 bg-folha"
              />
              <p className="text-xs text-grafite">
                Quem contratou a obra atestada. É por ele que as respostas identificam o contratante.
              </p>
            </div>

            {erro && <p className="rounded-md bg-erro-claro px-4 py-3 text-sm text-erro">{erro}</p>}

            {resultado && resultado.status === "simulado" && (
              <div className="flex items-start gap-3 rounded-md bg-alerta-claro px-4 py-3 text-sm text-alerta">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                <div>
                  <div className="font-bold">{resultado.arquivo} recebido · simulação</div>
                  <p className="mt-0.5">{resultado.mensagem}</p>
                </div>
              </div>
            )}
            {resultado && resultado.status !== "simulado" && (
              <div className="flex items-start gap-3 rounded-md border border-teal bg-teal-claro px-4 py-3 text-sm">
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-teal-texto" />
                <div>
                  <div className="font-bold">{resultado.arquivo} recebido</div>
                  <p className="mt-0.5 text-grafite">{resultado.mensagem}</p>
                </div>
              </div>
            )}

            <Button
              type="submit"
              className="h-10 w-full rounded-[4px] hover:bg-petroleo-hover"
              disabled={!arquivo || orgao.trim().length < 2 || enviando}
            >
              {enviando ? <Loader2 className="animate-spin" /> : <UploadCloud />}
              Enviar documento
            </Button>
          </form>

          <aside className="flex flex-col gap-5">
            <div className="rounded-md bg-folha p-5 text-sm leading-relaxed shadow-card">
              <div className="mb-2 flex items-center gap-2 font-bold">
                <Info className="size-4 text-teal-texto" /> O que acontece depois do envio
              </div>
              {demo ? (
                <p className="text-grafite">
                  <span className="font-bold text-alerta">Modo demonstração:</span> o envio é{" "}
                  <span className="font-bold text-tinta">simulado</span>. O arquivo é validado, mas nada é
                  guardado nem processado, e o acervo não muda.
                </p>
              ) : (
                <>
                  <p className="text-grafite">
                    O PDF é guardado e a indexação roda em segundo plano, em cinco etapas: triagem pelo
                    conteúdo, extração do texto, divisão em trechos, cadastro no acervo e indexação para busca.
                  </p>
                  <p className="mt-3 text-grafite">
                    Leva alguns minutos por documento, mais se o PDF for escaneado: páginas sem texto passam
                    por OCR, que é cobrado.
                  </p>
                </>
              )}
              <p className="mt-3 text-grafite">
                Um documento só aparece nas respostas depois que a situação dele no{" "}
                <span className="font-bold text-tinta">Acervo</span> estiver como{" "}
                <span className="font-bold text-tinta">Indexado</span>.
              </p>
            </div>
          </aside>
        </div>
        {envios.length > 0 && (
          <section className="mt-5 overflow-hidden rounded-md bg-folha shadow-card" aria-label="Envios recentes">
            <h2 className="border-b px-5 py-4 text-base font-bold">Envios desde que a API foi iniciada</h2>
            <ul className="divide-y">
              {envios.map((e) => (
                <ProgressoEnvio key={e.id} envio={e} onAprovar={aprovar} />
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
