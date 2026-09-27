import "server-only";
import { getCloudflareContext } from "@opennextjs/cloudflare";

/**
 * api Worker の呼び出しを集約する（設計書 3.1）。
 * - Workers 上: Service Binding（env.API.fetch）。api は公開URLを持たない
 * - ローカル（next dev）: API_BASE_URL（既定 http://127.0.0.1:8787）の uvicorn に中継
 */
export async function callApi(path: string, init: RequestInit = {}): Promise<Response> {
  const base = process.env.API_BASE_URL ?? (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8787" : undefined);
  if (base) {
    return fetch(new URL(path, base), init);
  }
  const { env } = await getCloudflareContext({ async: true });
  const api = (env as CloudflareEnv).API;
  if (!api) {
    throw new Error("API binding is not configured");
  }
  // Service Binding ではホスト名は使われないが、URL として有効な値が必要
  return api.fetch(new Request(new URL(path, "https://accounting-api.internal"), init));
}

export async function accessConfig(): Promise<{ teamDomain?: string; aud?: string; localBypass?: boolean }> {
  try {
    const { env } = await getCloudflareContext({ async: true });
    const e = env as CloudflareEnv;
    return {
      teamDomain: e.CF_ACCESS_TEAM_DOMAIN || process.env.CF_ACCESS_TEAM_DOMAIN || undefined,
      aud: e.CF_ACCESS_AUD || process.env.CF_ACCESS_AUD || undefined,
      localBypass: e.ACCESS_LOCAL_BYPASS === "true",
    };
  } catch {
    return { teamDomain: process.env.CF_ACCESS_TEAM_DOMAIN, aud: process.env.CF_ACCESS_AUD };
  }
}
