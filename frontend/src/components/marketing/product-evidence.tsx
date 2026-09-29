import { FileImage, Play } from "lucide-react";

export function ProductEvidence({
  title,
  description,
  asset,
}: {
  title: string;
  description: string;
  asset: string;
}) {
  return (
    <figure className="overflow-hidden border border-subtle bg-surface">
      <div className="flex aspect-[16/10] items-center justify-center bg-surface-muted p-8 text-center">
        <div className="max-w-xs">
          <FileImage className="mx-auto size-6 text-primary" aria-hidden="true" />
          <p className="mt-4 text-sm font-bold text-fg">Screenshot real pendente</p>
          <p className="mt-2 text-xs leading-5 text-muted">{asset}</p>
        </div>
      </div>
      <figcaption className="border-t border-subtle px-5 py-4">
        <strong className="text-sm text-fg">{title}</strong>
        <p className="mt-1 text-xs leading-5 text-muted">{description}</p>
      </figcaption>
    </figure>
  );
}

export function VideoTeaser() {
  const source = process.env.NEXT_PUBLIC_CORE_TEASER_URL;
  const poster = process.env.NEXT_PUBLIC_CORE_TEASER_POSTER_URL;

  if (source) {
    return (
      <video className="w-full border border-subtle bg-surface" controls preload="metadata" poster={poster}>
        <source src={source} type="video/mp4" />
        Seu navegador não suporta reprodução de vídeo.
      </video>
    );
  }

  return (
    <div className="flex aspect-video items-center justify-center border border-subtle bg-surface-muted p-8 text-center">
      <div className="max-w-sm">
        <Play className="mx-auto size-6 text-primary" aria-hidden="true" />
        <p className="mt-4 text-sm font-bold text-fg">Vídeo do CORE em preparação</p>
        <p className="mt-2 text-xs leading-5 text-muted">O player está pronto para receber o vídeo real em `public/site/videos/core-teaser.mp4` e seu poster otimizado.</p>
      </div>
    </div>
  );
}
