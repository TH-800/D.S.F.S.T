// SCRUM-12: a reusable display component, not a health-check client.
// The caller supplies the latest reachability result. Keeping network requests
// outside this component lets it work with the monitor, mock data or SCRUM-13.
// null means no result yet; it must not imply that a service is online.
import React from "react";

export interface ServiceStatusIndicatorProps {
  online: boolean | null;
  label?: string;
  mock?: boolean;
}

export default function ServiceStatusIndicator({
  online,
  label = "Service",
  mock = false,
}: ServiceStatusIndicatorProps) {
  const status = online === null ? "Not checked" : online ? "Online" : "Unreachable";
  const color = online === null
    ? "bg-slate-400"
    : online ? "bg-emerald-500" : "bg-red-500";

  return (
    <span
      className="inline-flex items-center gap-2 text-sm"
      role="status"
      aria-label={`${label}: ${status}${mock ? " (simulated)" : ""}`}
      data-testid="service-status-indicator"
      data-state={online === null ? "unknown" : online ? "online" : "offline"}
    >
      {/* Text accompanies the colored dot so color is never the only signal. */}
      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${color}`} aria-hidden="true" />
      <span>{label}</span>
      <span className="text-muted-foreground">{status}{mock ? " (simulated)" : ""}</span>
    </span>
  );
}
