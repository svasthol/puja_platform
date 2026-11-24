import { z } from "zod";

import { getAccessToken, getApiBase, getRefreshToken, setTokens } from "@/lib/auth/tokens";
import { tokenPairSchema } from "@/lib/schemas/auth";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public body?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const DEFAULT_FETCH_TIMEOUT_MS = 25_000;

function fetchWithTimeout(url: string, init: RequestInit, timeoutMs = DEFAULT_FETCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const ext = init.signal;
  if (ext) {
    if (ext.aborted) {
      controller.abort();
    } else {
      ext.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...init, signal: controller.signal }).finally(() => clearTimeout(timer));
}

async function parseJson(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

async function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;
  const res = await fetchWithTimeout(`${getApiBase()}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!res.ok) return null;
  const data = tokenPairSchema.parse(await parseJson(res));
  setTokens(data.access_token, data.refresh_token);
  return data.access_token;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit & { schema?: z.ZodType<T>; auth?: boolean } = {},
): Promise<T> {
  const { schema, auth = true, headers, ...rest } = options;
  const url = `${getApiBase()}${path.startsWith("/") ? path : `/${path}`}`;

  const run = async (token: string | null) => {
    const h = new Headers(headers);
    if (!h.has("Content-Type") && rest.body) {
      h.set("Content-Type", "application/json");
    }
    if (auth && token) {
      h.set("Authorization", `Bearer ${token}`);
    }
    return fetchWithTimeout(url, { ...rest, headers: h });
  };

  let token = auth ? getAccessToken() : null;
  let res: Response;
  try {
    res = await run(token);
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(
        "API request timed out. Is the backend running and reachable?",
        0,
      );
    }
    throw err;
  }

  if (auth && res.status === 401 && getRefreshToken()) {
    token = await refreshAccessToken();
    if (token) {
      try {
        res = await run(token);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          throw new ApiError(
            "API request timed out. Is the backend running and reachable?",
            0,
          );
        }
        throw err;
      }
    }
  }

  const body = await parseJson(res);
  if (!res.ok) {
    const detail =
      typeof body === "object" && body && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : res.statusText;
    throw new ApiError(detail || "Request failed", res.status, body);
  }

  if (schema) return schema.parse(body);
  return body as T;
}
