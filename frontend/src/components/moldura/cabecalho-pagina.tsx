/** Título grande + subtítulo cinza + ações à direita. */
export function CabecalhoPagina({
  titulo,
  subtitulo,
  acoes,
  antes,
}: {
  titulo: string;
  subtitulo?: React.ReactNode;
  acoes?: React.ReactNode;
  antes?: React.ReactNode;
}) {
  return (
    <div className="flex shrink-0 items-end justify-between gap-6 pb-5">
      <div className="min-w-0">
        {antes}
        <h1 className="text-[2.25rem] leading-tight font-light text-tinta">{titulo}</h1>
        {subtitulo && <p className="mt-1 text-sm text-grafite">{subtitulo}</p>}
      </div>
      {acoes && <div className="flex shrink-0 items-center gap-2 pb-1">{acoes}</div>}
    </div>
  );
}
