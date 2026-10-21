import { useEffect, useState } from "react";
import { fetchHealthData } from "@/lib/api";

type Connection = "checking" | "online" | "offline";

function LiveMonitorStatus() {
  const [connection, setConnection] = useState<Connection>("checking");

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let request: AbortController;

    async function poll() {
      request = new AbortController();
      try {
        await fetchHealthData(request.signal);
        if (!cancelled) setConnection("online");
      } catch {
        if (!cancelled) setConnection("offline");
      } finally {
        if (!cancelled) timer = setTimeout(poll, 5000);
      }
    }

    void poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      request?.abort();
    };
  }, []);

  const color = connection === "online" ? "bg-emerald-500" :
    connection === "offline" ? "bg-red-500" : "bg-yellow-500";
  const label = connection === "checking" ? "Checking monitor" : `Monitor ${connection}`;

  return (
    <span role="status" aria-live="polite" data-testid="monitor-health" className="inline-flex items-center gap-2 text-sm">
      <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${color}`} />
      {label}
    </span>
  );
}

export default function MonitorHealthIndicator({ isLiveMode }: { isLiveMode: boolean }) {
  // Unmount the live poller in mock mode so old requests cannot change its status.
  return isLiveMode ? <LiveMonitorStatus /> : (
    <span role="status" data-testid="monitor-health" className="text-sm text-muted-foreground">
      Monitor simulated
    </span>
  );
}
