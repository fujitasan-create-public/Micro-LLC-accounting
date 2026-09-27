import { verifyAccess } from "@/lib/access";
import { callApi } from "@/lib/api-client";

// ブラウザからは api を直接呼ばず、この Route Handler を経由する（設計書 3.1）
export const dynamic = "force-dynamic";

const FORWARD_REQUEST_HEADERS = ["content-type", "accept"];
const FORWARD_RESPONSE_HEADERS = ["content-type", "content-disposition"];

async function handle(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const auth = await verifyAccess(request);
  if (!auth.ok) {
    return Response.json({ error: { code: "forbidden", message: auth.reason } }, { status: 403 });
  }
  const { path } = await ctx.params;
  const url = new URL(request.url);
  const target = `/api/v1/${path.map(encodeURIComponent).join("/")}${url.search}`;
  const headers = new Headers();
  for (const h of FORWARD_REQUEST_HEADERS) {
    const v = request.headers.get(h);
    if (v) headers.set(h, v);
  }
  const hasBody = !["GET", "HEAD"].includes(request.method);
  let res: Response;
  try {
    res = await callApi(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
    });
  } catch (e) {
    return Response.json(
      { error: { code: "api_unreachable", message: `API に接続できません（${(e as Error).message}）` } },
      { status: 502 },
    );
  }
  const out = new Headers();
  for (const h of FORWARD_RESPONSE_HEADERS) {
    const v = res.headers.get(h);
    if (v) out.set(h, v);
  }
  out.set("cache-control", "no-store");
  return new Response(res.body, { status: res.status, headers: out });
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
