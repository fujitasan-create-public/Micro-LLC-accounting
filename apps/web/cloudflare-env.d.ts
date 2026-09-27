// `npm run cf-typegen` で再生成できる。ここでは使う分だけを最小限に定義している
interface CloudflareEnv {
  API?: { fetch(input: Request | string, init?: RequestInit): Promise<Response> };
  CF_ACCESS_TEAM_DOMAIN?: string;
  CF_ACCESS_AUD?: string;
}
