import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useGatewayHealth } from "@/modules/dashboard/hooks/use-health";

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("useGatewayHealth", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("resolves with the gateway health payload", async () => {
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

    const { result } = renderHook(() => useGatewayHealth(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.service).toBe("gateway");
  });
});
