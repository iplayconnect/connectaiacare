/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "i.pravatar.cc" },
      { protocol: "https", hostname: "images.unsplash.com" },
      { protocol: "https", hostname: "api.dicebear.com" },
      { protocol: "https", hostname: "ui-avatars.com" },
      { protocol: "https", hostname: "cdn.connectaia.com.br" },
      { protocol: "https", hostname: "cdn.connectaiacare.com" },
    ],
  },
  async rewrites() {
    return [
      {
        source: "/api-proxy/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:5055"}/api/:path*`,
      },
    ];
  },
  async redirects() {
    // URLs antigas → novas após reorganização do painel super_admin
    // (separação governance vs system, 2026-05-01). Mantém
    // bookmarks/links externos funcionando.
    return [
      // Governança clínica
      { source: "/admin/corpus-review", destination: "/admin/governance/corpus-review", permanent: true },
      { source: "/admin/regras-clinicas", destination: "/admin/governance/clinical-rules", permanent: true },
      { source: "/admin/regras-clinicas/cascadas", destination: "/admin/governance/cascades", permanent: true },
      { source: "/admin/regras-clinicas/revisao", destination: "/admin/governance/review", permanent: true },
      { source: "/admin/testes-sinteticos", destination: "/admin/governance/synthetic-tests", permanent: true },
      { source: "/admin/cenarios-sofia", destination: "/admin/governance/scenarios", permanent: true },
      { source: "/admin/cenarios-sofia/versoes", destination: "/admin/governance/scenarios/versions", permanent: true },
      // Sistema (cross-tenant, super_admin)
      { source: "/admin/saude", destination: "/admin/system/health", permanent: true },
      { source: "/admin/seguranca/risk-score", destination: "/admin/system/health/risk-score", permanent: true },
      { source: "/admin/proactive-caller", destination: "/admin/system/operations/proactive-caller", permanent: true },
    ];
  },
};

module.exports = nextConfig;
