/**
 * Centralized API client. Per docs/009_Frontend_Master_Architecture.md.txt,
 * no component or page may call `fetch()` directly — every backend call
 * goes through this module (or a module-level `services/` wrapper built on
 * top of it).
 */

import { env } from "@/config/env";
import type { ApiResponse } from "@/types/api";

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: string[];

  constructor(status: number, message: string, code: string, details: string[]) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface ApiClientOptions extends RequestInit {
  signal?: AbortSignal;
}

async function request<TData>(path: string, options: ApiClientOptions = {}): Promise<TData> {
  const requestId = crypto.randomUUID();
  const response = await fetch(`${env.apiBaseUrl}${path}`, {
    ...options,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Request-ID": requestId,
      "X-Correlation-ID": requestId,
      ...options.headers,
    },
  });

  const body = (await response.json()) as ApiResponse<TData>;

  if (!body.success) {
    throw new ApiRequestError(response.status, body.message, body.error.code, body.error.details);
  }

  return body.data;
}

export const apiClient = {
  get: <TData>(path: string, options?: ApiClientOptions) =>
    request<TData>(path, { ...options, method: "GET" }),
};
