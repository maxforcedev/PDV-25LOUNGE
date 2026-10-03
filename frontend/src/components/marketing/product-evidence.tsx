import { existsSync } from "node:fs";
import { join } from "node:path";
import Image from "next/image";

function hasAsset(src: string) {
  return existsSync(join(process.cwd(), "public", src.replace(/^\//, "")));
}

export function ProductEvidence({
  title,
  description,
  src,
  alt,
  priority = false,
  className = "",
}: {
  title: string;
  description?: string;
  src: string;
  alt: string;
  priority?: boolean;
  className?: string;
}) {
  const available = hasAsset(src);
  return (
    <figure className={`overflow-hidden border border-subtle bg-surface ${className}`}>
      <div className="relative aspect-[16/10] bg-[#dde5f4] dark:bg-[#202c3b]">
        {available ? (
          <Image src={src} alt={alt} fill priority={priority} sizes="(min-width: 1024px) 50vw, 100vw" className="object-contain" />
        ) : (
          <div className="absolute inset-0 flex items-end bg-[linear-gradient(135deg,#3454d1_0%,#3454d1_38%,#dde5f4_38%,#dde5f4_100%)] p-6 dark:bg-[linear-gradient(135deg,#2945b6_0%,#2945b6_38%,#202c3b_38%,#202c3b_100%)]" aria-hidden="true"><span className="text-4xl font-black tracking-[-0.08em] text-white/90">CORE</span></div>
        )}
      </div>
      {(title || description) && <figcaption className="border-t border-subtle px-5 py-4"><strong className="text-sm text-fg">{title}</strong>{description && <p className="mt-1 text-xs leading-5 text-muted">{description}</p>}</figcaption>}
    </figure>
  );
}

export function VideoTeaser() {
  const source = process.env.NEXT_PUBLIC_CORE_TEASER_URL;
  const poster = process.env.NEXT_PUBLIC_CORE_TEASER_POSTER_URL;
  if (!source) return null;
  return <video className="w-full border border-subtle bg-surface" controls preload="metadata" poster={poster}><source src={source} type="video/mp4" />Seu navegador não suporta reprodução de vídeo.</video>;
}

export function PaymentDevices() {
  const assets = [
    { src: "/site/images/payment-device-01.webp", alt: "Equipamento de pagamento utilizado na operação" },
    { src: "/site/images/payment-device-02.webp", alt: "Equipamento de pagamento em uso" },
    { src: "/site/images/payment-device-03.webp", alt: "Terminal de pagamento" },
  ].filter((asset) => hasAsset(asset.src));
  if (!assets.length) return null;
  return <div className="mt-10 flex snap-x gap-5 overflow-x-auto pb-2 [scrollbar-width:thin]">{assets.map((asset, index) => <div key={asset.src} className="relative h-52 w-[333px] shrink-0 snap-center overflow-hidden border border-subtle bg-surface sm:h-64 sm:w-[410px]"><Image src={asset.src} alt={asset.alt} fill sizes="(min-width: 640px) 410px, 333px" priority={index === 0} className="object-contain" /></div>)}</div>;
}
