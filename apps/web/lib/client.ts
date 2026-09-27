"use client";

import { useCallback, useEffect, useState } from "react";

export type Warning = { rule_id: string; message: string };

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
    public ruleId?: string,
  ) {
    super(message);
  }
}

const BASE = "/api/proxy";

type Options = {
  method?: string;
  body?: unknown;
  form?: FormData;
  query?: Record<string, string | number | boolean | undefined | null>;
};

export function buildUrl(path: string, query?: Options["query"]): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  }
  const s = qs.toString();
  return `${BASE}/${path.replace(/^\//, "")}${s ? `?${s}` : ""}`;
}

/** ブラウザから web の Route Handler（/api/proxy）経由で API を呼ぶ。 */
export async function api<T = any>(path: string, opts: Options = {}): Promise<T> {
  const init: RequestInit = { method: opts.method ?? (opts.body || opts.form ? "POST" : "GET") };
  if (opts.form) {
    init.body = opts.form;
  } else if (opts.body !== undefined) {
    init.body = JSON.stringify(opts.body);
    init.headers = { "content-type": "application/json" };
  }
  const res = await fetch(buildUrl(path, opts.query), init);
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const err = data?.error;
    throw new ApiError(err?.message ?? `エラーが発生しました（${res.status}）`, res.status, err?.code, err?.rule_id);
  }
  return data as T;
}

export function useApi<T = any>(path: string | null, query?: Options["query"]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(false);
  const key = path ? buildUrl(path, query) : null;

  const reload = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      setData(await api<T>(path, { query }));
      setError(null);
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { data, error, loading, reload, setData };
}

export const yen = (n: number | string | null | undefined): string => {
  if (n === null || n === undefined || n === "") return "";
  if (typeof n === "string") return n;
  return n.toLocaleString("ja-JP");
};

export const todayIso = (): string => {
  const d = new Date(Date.now() + 9 * 3600 * 1000);
  return d.toISOString().slice(0, 10);
};

export function downloadUrl(path: string, query?: Options["query"]): string {
  return buildUrl(path, query);
}
