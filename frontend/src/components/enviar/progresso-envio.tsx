import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import type { Envio, EtapaEnvio } from "@/lib/api";
import { cn } from "@/lib/utils";

const ESTADO_ENVIO: Record<Envio["estado"], { rotulo: string; badge: string }> = {
  na_fila: { rotulo: "Na fila", badge: "bg-alerta-claro text-alerta" },
  processando: { rotulo: "Em processamento", badge: "bg-alerta-claro text-alerta" },
  concluido: { rotulo: "Indexado", badge: "bg-teal-texto text-white" },
  erro: { rotulo: "Erro", badge: "bg-erro-claro text-erro" },
};

function IconeEtapa({ estado }: { estado: EtapaEnvio["estado"] }) {
  if (estado === "ok") return <CheckCircle2 className="size-4 text-teal-texto" aria-hidden />;
  if (estado === "erro") return <XCircle className="size-4 text-erro" aria-hidden />;
  if (estado === "andamento") return <Loader2 className="size-4 animate-spin text-alerta" aria-hidden />;
  return <Circle className="size-4 text-linha" aria-hidden />;
}

const AGUARDANDO = { rotulo: "Aguardando aprovação", badge: "bg-alerta-claro text-alerta" };

/** Um envio real e as etapas do pipeline, como a API relata em GET /uploads/{id}. */
export function ProgressoEnvio({ envio, onAprovar }: { envio: Envio; onAprovar?: (id: string) => void }) {
  const e = envio.aguardando_aprovacao ? AGUARDANDO : ESTADO_ENVIO[envio.estado];
  const hora = new Date(envio.criado_em).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return (
    <li className="px-5 py-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-[11px] font-bold tracking-[0.08em] text-grafite uppercase">{envio.orgao}</div>
          <div className="truncate font-bold">{envio.titulo ?? envio.arquivo}</div>
          <div className="text-xs text-grafite">
            {envio.arquivo} · enviado às {hora}
          </div>
        </div>
        <span className={cn("shrink-0 rounded-full px-2.5 py-0.5 text-xs font-bold", e.badge)}>{e.rotulo}</span>
      </div>
      <ol className="mt-3 flex flex-col gap-1.5" aria-label={`Etapas de ${envio.arquivo}`}>
        {envio.etapas.map((etapa) => (
          <li key={etapa.chave} className="flex items-start gap-2 text-sm">
            <span className="mt-0.5">
              <IconeEtapa estado={etapa.estado} />
            </span>
            <span className={cn(etapa.estado === "pendente" && "text-grafite")}>
              {etapa.rotulo}
              {etapa.detalhe && (
                <span className={cn("text-grafite", etapa.estado === "erro" && "text-erro")}> · {etapa.detalhe}</span>
              )}
            </span>
          </li>
        ))}
      </ol>
      {envio.aguardando_aprovacao && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-md bg-alerta-claro px-3 py-2 text-sm">
          <span className="text-alerta">{envio.erro ?? "Este documento precisa de OCR pago acima do teto por envio."}</span>
          {onAprovar && (
            <button
              type="button"
              onClick={() => onAprovar(envio.id)}
              className="shrink-0 rounded-md bg-petroleo px-3 py-1.5 font-bold text-white hover:bg-petroleo-hover"
            >
              Aprovar OCR
            </button>
          )}
        </div>
      )}
    </li>
  );
}
