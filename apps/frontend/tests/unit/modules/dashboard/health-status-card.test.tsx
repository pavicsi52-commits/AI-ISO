import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HealthStatusCard } from "@/modules/dashboard/components/health-status-card";
import { useGatewayHealth } from "@/modules/dashboard/hooks/use-health";

vi.mock("@/modules/dashboard/hooks/use-health", () => ({
  useGatewayHealth: vi.fn(),
}));

const mockedUseGatewayHealth = vi.mocked(useGatewayHealth);

describe("HealthStatusCard", () => {
  it("shows a loading message while fetching", () => {
    mockedUseGatewayHealth.mockReturnValue({
      isLoading: true,
      isError: false,
      data: undefined,
      error: null,
    } as ReturnType<typeof useGatewayHealth>);

    render(<HealthStatusCard />);

    expect(screen.getByText(/checking gateway status/i)).toBeInTheDocument();
  });

  it("shows an error state when the gateway is unreachable", () => {
    mockedUseGatewayHealth.mockReturnValue({
      isLoading: false,
      isError: true,
      data: undefined,
      error: new Error("Failed to fetch"),
    } as ReturnType<typeof useGatewayHealth>);

    render(<HealthStatusCard />);

    expect(screen.getByText("Unreachable")).toBeInTheDocument();
    expect(screen.getByText("Failed to fetch")).toBeInTheDocument();
  });

  it("shows health details on success", () => {
    mockedUseGatewayHealth.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { status: "healthy", service: "gateway", version: "0.1.0", environment: "development" },
      error: null,
    } as ReturnType<typeof useGatewayHealth>);

    render(<HealthStatusCard />);

    expect(screen.getByText("healthy")).toBeInTheDocument();
    expect(screen.getByText("gateway")).toBeInTheDocument();
    expect(screen.getByText("0.1.0")).toBeInTheDocument();
    expect(screen.getByText("development")).toBeInTheDocument();
  });
});
