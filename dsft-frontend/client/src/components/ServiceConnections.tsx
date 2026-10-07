// SCRUM-12 integration, generated with OpenAI Codex assistance.
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import ServiceStatusIndicator from "./ServiceStatusIndicator";
import { fetchStatusData, getMockStatusData, type StatusData } from "@/lib/api";

const services = [
  [8001, "Network monitoring"], [8002, "CPU monitoring"], [8003, "Memory monitoring"],
  [8004, "CPU injection"], [8005, "Latency injection"], [8006, "Packet loss injection"],
  [8007, "Memory injection"], [8008, "Metrics and presets"],
  [8009, "Experiment orchestrator"], [8010, "Reports"],
] as const;

export default function ServiceConnections({ live }: { live: boolean }) {
  const [status, setStatus] = useState<StatusData | null>(null);
  const [monitorOnline, setMonitorOnline] = useState<boolean | null>(null);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      try {
        const result = live ? await fetchStatusData(controller.signal) : getMockStatusData();
        if (cancelled) return;
        setStatus(result);
        setMonitorOnline(true);
      } catch {
        if (cancelled) return;
        setStatus(null);
        setMonitorOnline(false);
      }
      // Wait for completion before scheduling: slow calls cannot overlap.
      if (!cancelled && live) timer = setTimeout(poll, 5000);
    }
    void poll();
    return () => { cancelled = true; controller.abort(); clearTimeout(timer); };
  }, [live]);

  return (
    <Card>
      <CardHeader><CardTitle className="text-sm font-medium">Service connection lights</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          {live ? "Service availability reported by this VM’s monitor. Green does not mean an experiment is running." : "Simulated service results in Mock mode."}
        </p>
        <ServiceStatusIndicator label="Service monitor (8000)" online={monitorOnline} mock={!live} />
        {live && monitorOnline === false && <p role="alert" className="text-sm text-red-500">
          Cannot reach the monitor. Other service states are unknown until it reconnects.
        </p>}
        <ul className="grid gap-3 md:grid-cols-2" aria-label="Backend service reachability">
          {services.map(([port, label]) => <li key={port}>
            <ServiceStatusIndicator label={`${label} (${port})`}
              online={typeof status?.services?.[String(port)]?.online === "boolean"
                ? status.services[String(port)].online : null} mock={!live} />
          </li>)}
        </ul>
        <p className="text-xs text-muted-foreground">Green: online · Red: unavailable · Grey: not checked</p>
      </CardContent>
    </Card>
  );
}
