import "server-only";
import { createRemoteJWKSet, jwtVerify } from "jose";
import { accessConfig } from "./api-client";

const jwksCache = new Map<string, ReturnType<typeof createRemoteJWKSet>>();

/**
 * Cloudflare Access が付与する Cf-Access-Jwt-Assertion を検証する（設計書 4章の二重チェック）。
 * ローカル開発（NODE_ENV=development）では検証しない。
 * 本番で Access の設定値（CF_ACCESS_TEAM_DOMAIN, CF_ACCESS_AUD）が無い場合は、安全側に倒して拒否する。
 */
export async function verifyAccess(request: Request): Promise<{ ok: true } | { ok: false; reason: string }> {
  if (process.env.NODE_ENV === "development") return { ok: true };
  const { teamDomain, aud, localBypass } = await accessConfig();
  // wrangler のローカル実行（.dev.vars で ACCESS_LOCAL_BYPASS=true）かつ localhost へのアクセスのときだけ省略する
  const host = new URL(request.url).hostname;
  if (localBypass && (host === "localhost" || host === "127.0.0.1")) return { ok: true };
  if (!teamDomain || !aud) return { ok: false, reason: "Cloudflare Access is not configured" };
  const token = request.headers.get("cf-access-jwt-assertion");
  if (!token) return { ok: false, reason: "missing access token" };
  const issuer = `https://${teamDomain}`;
  let jwks = jwksCache.get(issuer);
  if (!jwks) {
    jwks = createRemoteJWKSet(new URL(`${issuer}/cdn-cgi/access/certs`));
    jwksCache.set(issuer, jwks);
  }
  try {
    await jwtVerify(token, jwks, { issuer, audience: aud });
    return { ok: true };
  } catch {
    return { ok: false, reason: "invalid access token" };
  }
}
