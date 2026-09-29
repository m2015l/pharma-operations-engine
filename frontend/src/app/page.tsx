"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowUp, Loader2, RotateCcw, SearchX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useConversa, type Turno } from "@/components/conversa-provider";
import { PainelFontes } from "@/components/consulta/painel-fontes";
import { SeloRastreio } from "@/components/consulta/selo-rastreio";
import { TextoResposta } from "@/components/consulta/texto-resposta";
import { VisualizadorFonte, type AlvoFonte } from "@/components/visualizador-fonte";
import { api } from "@/lib/api";
import { CabecalhoPagina } from "@/components/moldura/cabecalho-pagina";
import { cn } from "@/lib/utils";

export default function PaginaConsulta() {
  const { turnos, carregando, selecao, perguntar, selecionar, novaConsulta } = useConversa();
  const [alvoFonte, setAlvoFonte] = useState<AlvoFonte | null>(null);
  const rolagemRef = useRef<HTMLDivElement>(null);

  // Rola só o card da conversa (scrollIntoView também rolaria os ancestrais).
  useEffect(() => {
    const el = rolagemRef.current;
    el?.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [turnos.length, carregando]);

  const indiceSelecionado = turnos.findIndex((t) => t.id === selecao?.turnoId);
  const turnoSelecionado = indiceSelecionado >= 0 ? turnos[indiceSelecionado] : null;

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-[1480px] flex-col px-8 pt-7 pb-1 xl:px-12">
      <CabecalhoPagina
        titulo="Consulta ao acervo"
        subtitulo="Toda resposta indica o documento e a página de onde a informação saiu."
        acoes={
          turnos.length > 0 && (
            <Button variant="outline" onClick={novaConsulta} disabled={carregando} className="h-9 px-3.5">
              <RotateCcw /> Nova consulta
            </Button>
          )
        }
      />

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,3fr)_minmax(380px,2fr)] gap-5">
        <section
          aria-label="Conversa"
          className="flex min-h-0 flex-col overflow-hidden rounded-md bg-folha shadow-card"
        >
          <div ref={rolagemRef} className="min-h-0 flex-1 overflow-y-auto">
            <div className="flex flex-col gap-8 px-7 py-7">
              {turnos.length === 0 && <EstadoVazio onEscolher={perguntar} />}
              {turnos.map((t, i) => (
                <BlocoTurno
                  key={t.id}
                  turno={t}
                  numero={i + 1}
                  selecionado={selecao?.turnoId === t.id}
                  marcadorAtivo={selecao?.turnoId === t.id ? selecao.marcador : null}
                  onMarcador={(n) => selecionar(t.id, n)}
                  onSelecionar={() => selecionar(t.id)}
                />
              ))}
            </div>
          </div>

          <Compositor onEnviar={perguntar} carregando={carregando} temHistorico={turnos.some((t) => t.resposta)} />
        </section>

        <PainelFontes
          resposta={turnoSelecionado?.resposta ?? null}
          indicePergunta={turnoSelecionado ? indiceSelecionado + 1 : null}
          marcadorAtivo={selecao?.marcador ?? null}
          onMarcador={(n) => turnoSelecionado && selecionar(turnoSelecionado.id, n)}
          onVerFonte={setAlvoFonte}
        />
      </div>

      <VisualizadorFonte alvo={alvoFonte} onFechar={() => setAlvoFonte(null)} />
    </div>
  );
}

function EstadoVazio({ onEscolher }: { onEscolher: (p: string) => void }) {
  const [sugestoes, setSugestoes] = useState<string[]>([]);
  useEffect(() => {
    api.sugestoes().then(setSugestoes).catch(() => setSugestoes([]));
  }, []);

  return (
    <div className="pt-2">
      <h2 className="text-2xl leading-tight font-bold">O que você precisa comprovar?</h2>
      <p className="mt-2 max-w-xl text-[15px] leading-relaxed text-grafite">
        Pergunte sobre obras, quantitativos, responsáveis técnicos ou valores. Toda resposta indica o
        documento e a página de onde a informação saiu.
      </p>
      {sugestoes.length > 0 && (
        <div className="mt-7">
          <div className="mb-2 text-sm text-grafite">Exemplos</div>
          <ul className="divide-y overflow-hidden rounded-md border">
            {sugestoes.map((s, i) => (
              <li key={s}>
                <button
                  type="button"
                  onClick={() => onEscolher(s)}
                  className="flex w-full items-baseline gap-4 px-4 py-3 text-left text-[15px] transition-colors hover:bg-teal-claro"
                >
                  <span className="w-5 shrink-0 text-grafite tabular-nums">{i + 1}</span>
                  {s}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

type PropsTurno = {
  turno: Turno;
  numero: number;
  selecionado: boolean;
  marcadorAtivo: number | null;
  onMarcador: (n: number) => void;
  onSelecionar: () => void;
};

function BlocoTurno({ turno, numero, selecionado, marcadorAtivo, onMarcador, onSelecionar }: PropsTurno) {
  const r = turno.resposta;
  return (
    <article aria-label={`Pergunta ${numero}`} className="flex flex-col gap-3">
      <div className="flex items-baseline gap-3">
        <span className="w-7 shrink-0 text-sm text-grafite tabular-nums">{String(numero).padStart(2, "0")}</span>
        <p className="text-[17px] leading-snug font-bold">{turno.pergunta}</p>
      </div>

      {!r && !turno.erro && (
        <div className="ml-10 flex items-center gap-2 text-sm text-grafite">
          <Loader2 className="size-4 animate-spin" /> Consultando o acervo…
        </div>
      )}

      {turno.erro && (
        <div className="ml-10 flex items-start gap-2 rounded-md bg-erro-claro px-4 py-3 text-sm text-erro">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {turno.erro}
        </div>
      )}

      {r && (
        <div
          onClick={onSelecionar}
          className={cn(
            "ml-10 cursor-default rounded-md border bg-folha px-6 pt-5 pb-3 transition-colors",
            selecionado ? "border-teal border-l-[3px] pl-[22px]" : "",
          )}
        >
          {!r.encontrou_no_acervo && (
            <div className="mb-3">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-escuro px-2.5 py-0.5 text-xs font-bold text-white">
                <SearchX className="size-3.5" /> Nada encontrado no acervo
              </span>
            </div>
          )}
          {r.encontrou_no_acervo && !r.contrato_citacao_ok && (
            <div className="mb-4 flex items-start gap-2 rounded-md bg-alerta-claro px-3 py-2.5 text-sm text-alerta">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <span>
                <strong>Resposta sem fonte rastreável.</strong>{" "}
                {r.citacoes_invalidas.length > 0
                  ? `O agente citou trechos que não existem (${r.citacoes_invalidas.join(", ")}).`
                  : "O agente não citou nenhum trecho."}{" "}
                Não use sem conferir no documento.
              </span>
            </div>
          )}

          <TextoResposta
            texto={r.texto}
            citacoes={r.citacoes}
            marcadorAtivo={marcadorAtivo}
            onMarcador={onMarcador}
          />

          <div className="mt-5 flex items-center justify-between gap-4 border-t pt-3">
            {r.encontrou_no_acervo ? <SeloRastreio resposta={r} /> : <span />}
            {r.modo === "demo" && r.origem && (
              <span className="truncate text-xs text-grafite" title={r.origem}>
                Resposta gravada · {resumoOrigem(r.origem)}
              </span>
            )}
          </div>
        </div>
      )}
    </article>
  );
}

function resumoOrigem(origem: string) {
  const data = origem.match(/(\d{4})-(\d{2})-(\d{2})/);
  const turno = origem.match(/turno (\d+\.\d+)/);
  if (data && turno) return `auditoria de ${data[3]}/${data[2]}, turno ${turno[1]}`;
  return origem;
}

function Compositor({
  onEnviar,
  carregando,
  temHistorico,
}: {
  onEnviar: (p: string) => void;
  carregando: boolean;
  temHistorico: boolean;
}) {
  const [texto, setTexto] = useState("");
  const enviar = () => {
    const p = texto.trim();
    if (!p || carregando) return;
    onEnviar(p);
    setTexto("");
  };

  return (
    <div className="shrink-0 border-t bg-folha px-7 py-4">
      <div>
        <div className="flex items-end gap-2 rounded-md border border-input bg-folha p-2 focus-within:border-teal focus-within:shadow-[0_0_0_3px_var(--teal-claro)]">
          <Textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                enviar();
              }
            }}
            rows={1}
            placeholder={temHistorico ? "Pergunte mais sobre isso, ou mude de assunto…" : "Pergunte ao acervo…"}
            aria-label="Pergunta"
            className="max-h-40 min-h-10 resize-none border-0 bg-transparent px-2 py-2 text-[15px] shadow-none focus-visible:ring-0"
          />
          <Button
            onClick={enviar}
            disabled={!texto.trim() || carregando}
            className="h-10 rounded-[4px] px-4 hover:bg-petroleo-hover"
            aria-label="Perguntar"
          >
            {carregando ? <Loader2 className="animate-spin" /> : <ArrowUp />}
            Perguntar
          </Button>
        </div>
        <p className="mt-2 text-xs text-grafite">
          Enter envia · Shift+Enter quebra linha · a conversa anterior é usada para entender “disso”, “dessa obra”.
        </p>
      </div>
    </div>
  );
}
