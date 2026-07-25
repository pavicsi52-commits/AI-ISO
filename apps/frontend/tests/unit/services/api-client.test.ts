import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient, ApiRequestError } from "@/services/api-client";

function mockFetchOnce(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      status,
      json: () => Promise.resolve(body),
    }),
  );
}

describe("apiClient.get", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the data payload on a successful response", async () => {
    mockFetchOnce(200, {
      success: true,
      message: "ok",
      data: { status: "healthy" },
      meta: { request_id: "abc", timestamp: "2026-01-01T00:00:00Z" },
    });

    const result = await apiClient.get<{ status: string }>("/health");

    expect(result).toEqual({ status: "healthy" });
  });

  it("sends request ID and correlation ID headers", async () => {
    mockFetchOnce(200, {
      success: true,
      message: "ok",
      data: {},
      meta: { request_id: "abc", timestamp: "2026-01-01T00:00:00Z" },
    });

    await apiClient.get("/health");

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(init.headers["X-Request-ID"]).toBeTruthy();
    expect(init.headers["X-Correlation-ID"]).toBe(init.headers["X-Request-ID"]);
  });

  it("throws ApiRequestError with structured details on failure", async () => {
    mockFetchOnce(503, {
      success: false,
      message: "Service is not ready.",
      error: { code: "AIIOS-GATEWAY-0001", details: ["dependency down"] },
      meta: { request_id: "abc", timestamp: "2026-01-01T00:00:00Z" },
    });

    await expect(apiClient.get("/readiness")).rejects.toMatchObject({
      status: 503,
      code: "AIIOS-GATEWAY-0001",
      details: ["dependency down"],
      message: "Service is not ready.",
    });
    await expect(apiClient.get("/readiness")).rejects.toBeInstanceOf(ApiRequestError);
  });
});
