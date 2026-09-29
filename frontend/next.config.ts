import type { NextConfig } from "next";

// O navegador só fala com o Next; o Next repassa /api/* para a API Python.
// Assim nenhuma URL/chave de backend vai para o código do navegador e não há CORS.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  devIndicators: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
