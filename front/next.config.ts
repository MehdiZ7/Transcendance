import { lstatSync } from "node:fs";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {
    serverActions: {
      bodySizeLimit: "8mb",
    },
  },
  images: {
    // Only the 42 avatars are remote (backend allowed_image_hosts, nginx CSP
    // img-src): the optimizer must not fetch from any other host.
    remotePatterns: [
      {
        protocol: "https",
        hostname: "cdn.intra.42.fr",
        port: "",
      },
    ],
  },
  // TODO: à supprimer — workaround temporaire pour que turbopack résolve
  // node_modules via le symlink vers ../sgoinfre. Inutile en environnement propre.
  // Appliqué seulement si node_modules est un symlink : sinon root "/" fait
  // générer le standalone sous .next/standalone/app/ et casse `node server.js`.
  ...(nodeModulesIsSymlink() && { turbopack: { root: "/" } }),
};

function nodeModulesIsSymlink(): boolean {
  try {
    return lstatSync("node_modules").isSymbolicLink();
  } catch {
    return false;
  }
}

export default nextConfig;
