import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // リポジトリ外（ホームディレクトリなど）の lockfile をルートと誤認しないようにする
  turbopack: { root: path.join(__dirname) },
};

export default nextConfig;

// next dev でローカルのバインディング（wrangler.jsonc）を使えるようにする
import { initOpenNextCloudflareForDev } from "@opennextjs/cloudflare";
initOpenNextCloudflareForDev();
