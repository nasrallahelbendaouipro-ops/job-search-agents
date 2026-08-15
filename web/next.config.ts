import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Sortie autonome : l'image Docker n'embarque pas node_modules en entier.
  output: "standalone",
};

export default nextConfig;
