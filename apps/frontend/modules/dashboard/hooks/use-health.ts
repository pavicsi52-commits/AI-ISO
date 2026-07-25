import { useQuery } from "@tanstack/react-query";

import { healthService } from "../services/health-service";

export function useGatewayHealth() {
  return useQuery({
    queryKey: ["gateway", "health"],
    queryFn: healthService.getGatewayHealth,
    refetchInterval: 15_000,
  });
}
