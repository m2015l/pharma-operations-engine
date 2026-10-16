import Image from "next/image";

/** Logo oficial Pharma Operations Platform (public/logo.png, 600×100, fundo transparente). */
export function Logo({ altura = 34 }: { altura?: number }) {
  return (
    <Image
      src="/logo.png"
      alt="Pharma Operations Platform"
      width={600}
      height={100}
      priority
      style={{ height: altura, width: "auto" }}
    />
  );
}
