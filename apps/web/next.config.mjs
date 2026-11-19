/** @type {import('next').NextConfig} */
const config = {
  async rewrites() {
    if (
      process.env.API_ORIGIN &&
      !process.env.API_ORIGIN.includes("127.0.0.1") &&
      !process.env.API_ORIGIN.includes("localhost")
    ) {
      return [
        {
          source: "/api/:path*",
          destination: `${process.env.API_ORIGIN}/api/:path*`,
        },
      ];
    }
    return [];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
          {
            key: "Content-Security-Policy",
            value:
              "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' *; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
          },
        ],
      },
    ];
  },
};

export default config;
