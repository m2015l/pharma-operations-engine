import Image from "next/image";

/** Logo oficial SOLUFARMA ENGENHARIA (public/logo.png, 600×100, fundo transparente). */
export function Logo({ altura = 34 }: { altura?: number }) {
  return (
    <Image
      src="/logo.png"
      alt="Solufarma Engenharia"
      width={600}
      height={100}
      priority
      style={{ height: altura, width: "auto" }}
    />
  );
}
