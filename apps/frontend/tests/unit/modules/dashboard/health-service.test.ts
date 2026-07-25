import { afterEach, describe, expect, it, vi } from "vitest";

import { healthService } from "@/modules/dashboard/services/health-service";

describe("healthService.getGatewayHealth", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requests the gateway's /health endpoint and returns its data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 200,
        json: () =>
          Promise.resolve({
            success: true,
            message: "ok",
            data: {
              status: "healthy",
              service: "gateway",
              version: "0.1.0",
              environment: "development",
            },
            meta: { request_id: "abc", timestamp: "2026-01-01T00:00:00Z" },
          }),
      }),
    );

    const result = await healthService.getGatewayHealth();

    expect(result.status).toBe("healthy");
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/health");
  });
});
