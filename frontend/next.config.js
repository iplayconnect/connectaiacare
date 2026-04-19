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
};

module.exports = nextConfig;
