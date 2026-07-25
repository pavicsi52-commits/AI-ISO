import { HealthStatusCard } from "./health-status-card";

export function DashboardPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground text-sm">
          Platform foundation is running. Business modules are not yet implemented.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <HealthStatusCard />
      </div>
    </div>
  );
}
