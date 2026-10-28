import "./src/env.js";

const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000";

/** @type {import("next").NextConfig} */
const config = {
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${BACKEND_URL}/api/v1/:path*` },
      {
        source: '/api/:path*',
        destination: `${BACKEND_URL}/:path*`,
      },
    ];
  },
};

export default config;
