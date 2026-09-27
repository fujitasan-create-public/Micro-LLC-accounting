import { defineCloudflareConfig } from "@opennextjs/cloudflare";
import kvIncrementalCache from "@opennextjs/cloudflare/overrides/incremental-cache/kv-incremental-cache";

// 会計データは毎回 API から取得し、ISR などの静的キャッシュは使わない（設計書 3.1）
export default defineCloudflareConfig({
  incrementalCache: kvIncrementalCache,
});
