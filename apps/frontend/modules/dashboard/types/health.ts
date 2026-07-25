export interface GatewayHealth {
  status: "healthy";
  service: string;
  version: string;
  environment: string;
}
