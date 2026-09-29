import { toast } from "sonner";
import { api, type TurnoExportado } from "@/lib/api";
import type { Turno } from "@/components/conversa-provider";

/** Turnos que entram no .docx: os que têm resposta ou erro (o em andamento fica de fora). */
export function turnosExportaveis(turnos: Turno[]) {
  return turnos.filter((t) => t.resposta || t.erro);
}

function paraExportacao(t: Turno): TurnoExportado {
  return {
    pergunta: t.pergunta,
    perguntado_em: t.perguntadoEm,
    resposta: t.resposta ?? null,
    erro: t.erro ?? null,
  };
}

/**
 * Gera o .docx na API e dispara o download (blob → <a download>).
 * `escopo: "resposta"` exporta um único turno, para colar no envelope da licitação.
 */
export async function exportarDocx(turnos: Turno[], escopo: "conversa" | "resposta") {
  const selecionados = turnosExportaveis(turnos);
  if (selecionados.length === 0) return;
  try {
    const { blob, nome } = await api.exportarDocx({
      escopo,
      gerado_em: new Date().toISOString(),
      turnos: selecionados.map(paraExportacao),
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = nome;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast.success(`${nome} baixado`, {
      description:
        escopo === "conversa"
          ? `${selecionados.length} ${selecionados.length === 1 ? "pergunta" : "perguntas"} exportadas para Word.`
          : "Resposta exportada para Word.",
    });
  } catch (e) {
    toast.error("Não foi possível exportar para Word", {
      description: e instanceof Error ? e.message : undefined,
    });
  }
}
