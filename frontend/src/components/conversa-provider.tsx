"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, type Resposta, type Saude } from "@/lib/api";

export type Turno = {
  id: string;
  pergunta: string;
  resposta?: Resposta;
  erro?: string;
};

type Selecao = { turnoId: string; marcador: number | null };

type Ctx = {
  turnos: Turno[];
  carregando: boolean;
  selecao: Selecao | null;
  /** undefined = ainda verificando; null = a API não respondeu. */
  saude: Saude | null | undefined;
  perguntar: (pergunta: string) => Promise<void>;
  selecionar: (turnoId: string, marcador?: number | null) => void;
  novaConsulta: () => void;
};

const ConversaCtx = createContext<Ctx | null>(null);

// Mesmo corte que a API aplica: o histórico entra inteiro no prompt de reescrita (I8).
const TURNOS_NO_HISTORICO = 6;

/**
 * Estado da conversa no layout raiz: sobrevive à navegação entre Consulta,
 * Acervo e Enviar documento. O histórico enviado ao agente é o que resolve
 * "e o valor disso?" — sem ele, o pronome chega sem antecedente.
 */
export function ConversaProvider({ children }: { children: React.ReactNode }) {
  const [turnos, setTurnos] = useState<Turno[]>([]);
  const [carregando, setCarregando] = useState(false);
  const [selecao, setSelecao] = useState<Selecao | null>(null);
  const [saude, setSaude] = useState<Saude | null | undefined>(undefined);

  useEffect(() => {
    api.saude().then(setSaude).catch(() => setSaude(null));
  }, []);

  const perguntar = useCallback(
    async (pergunta: string) => {
      const id = crypto.randomUUID();
      const historico = turnos
        .filter((t) => t.resposta)
        .slice(-TURNOS_NO_HISTORICO)
        .map((t) => ({ pergunta: t.pergunta, resposta: t.resposta!.texto }));

      setTurnos((ts) => [...ts, { id, pergunta }]);
      setCarregando(true);
      try {
        const resposta = await api.perguntar(pergunta, historico);
        setTurnos((ts) => ts.map((t) => (t.id === id ? { ...t, resposta } : t)));
        setSelecao({ turnoId: id, marcador: null });
      } catch (e) {
        const erro = e instanceof Error ? e.message : "Falha ao consultar o acervo.";
        setTurnos((ts) => ts.map((t) => (t.id === id ? { ...t, erro } : t)));
      } finally {
        setCarregando(false);
      }
    },
    [turnos],
  );

  const selecionar = useCallback((turnoId: string, marcador: number | null = null) => {
    setSelecao({ turnoId, marcador });
  }, []);

  const novaConsulta = useCallback(() => {
    setTurnos([]);
    setSelecao(null);
  }, []);

  const valor = useMemo(
    () => ({ turnos, carregando, selecao, saude, perguntar, selecionar, novaConsulta }),
    [turnos, carregando, selecao, saude, perguntar, selecionar, novaConsulta],
  );
  return <ConversaCtx.Provider value={valor}>{children}</ConversaCtx.Provider>;
}

export function useConversa() {
  const ctx = useContext(ConversaCtx);
  if (!ctx) throw new Error("useConversa fora do ConversaProvider");
  return ctx;
}
