import type { NextConfig } from "next";

// Every page here is behind a login and reads live data, so the app renders
// per request; Cache Components / prerendered shells are deliberately off.
const nextConfig: NextConfig = {
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
