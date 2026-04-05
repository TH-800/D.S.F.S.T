// Dashboard.tsx - the main dashboard page where we show all the system stats
// we pull data from the FastAPI backend every 5 seconds to keep things updated
// theres a toggle to switch between mock data and live API data

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Cpu, MemoryStick, Wifi, Clock, Activity, Server } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { useAppState } from "@/lib/store";
import {
  getMockCpuData,
  getMockMemoryData,
  getMockNetworkData,
  getMockHealthData,
  getMockStatusData,
  fetchCpuData,
  fetchMemoryData,
  fetchNetworkData,
  fetchHealthData,
  fetchStatusData,
  fetchLatestMetrics,
  fetchOrchestratorState,
  type CpuData,
  type MemoryData,
  type NetworkData,
  type HealthData,
  type StatusData,
  type OrchestratorState,
} from "@/lib/api";

// figures out what color to show based on a percentage value
// green = good, yellow = warning, red = danger
function getStatusColor(value: number, thresholds: { warn: number; danger: number }) {
  if (value >= thresholds.danger) return "destructive";
  if (value >= thresholds.warn) return "warning";
  return "good";
}

// returns the right tailwind classes for our status colors
function getStatusClasses(status: string) {
  switch (status) {
    case "destructive":
      return {
        text: "text-red-500",
        bg: "bg-red-500/10",
        border: "border-red-500/20",
        progress: "bg-red-500",
      };
    case "warning":
      return {
        text: "text-yellow-500",
        bg: "bg-yellow-500/10",
        border: "border-yellow-500/20",
        progress: "bg-yellow-500",
      };
    default:
      return {
        text: "text-emerald-500",
        bg: "bg-emerald-500/10",
        border: "border-emerald-500/20",
        progress: "bg-emerald-500",
      };
  }
}

// formats an ISO timestamp into something more readable
function formatTime(ts: string) {
  try {
    let isoStr = ts;
    if (!ts.includes("T") && !ts.includes("Z")) {
      isoStr = ts.replace(" ", "T") + "Z";
    }
    const d = new Date(isoStr);
    return d.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "N/A";
  }
}

export default function Dashboard() {
  const { isLiveMode, setIsLiveMode, addLog } = useAppState();

  // state for the three metric types
  const [cpuData, setCpuData] = useState<CpuData | null>(null);
  const [memData, setMemData] = useState<MemoryData | null>(null);
  const [netData, setNetData] = useState<NetworkData | null>(null);
  const [healthData, setHealthData] = useState<HealthData | null>(null);
  const [statusData, setStatusData] = useState<StatusData | null>(null);
  const [lastUpdate, setLastUpdate] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  // orchestrator state from port 8009 - shows us the experiment lifecycle state machine
  const [orchestratorState, setOrchestratorState] = useState<OrchestratorState | null>(null);

  // fetches all the metrics - either from mock or the real API
  // in live mode we also try the MetricsAPI (port 8008) as a fallback for the direct
  // monitoring endpoints, and we grab the orchestrator state from port 8009
  const refreshData = useCallback(async () => {
    try {
      setError(null);
      if (isLiveMode) {
        // try to hit the actual FastAPI endpoints first (direct monitoring scripts)
        // and also grab the orchestrator state in parallel
        const results = await Promise.allSettled([
          fetchCpuData(),
          fetchMemoryData(),
          fetchNetworkData(),
          fetchHealthData(),
          fetchStatusData(),
          fetchOrchestratorState(),
        ]);

        const [cpuResult, memResult, netResult, healthResult, statusResult, orchResult] = results;

        // if the direct monitoring endpoints (ports 8001-8003) failed, try MetricsAPI as backup
        // the MetricsAPI reads the same data from InfluxDB so it should be close enough
        let usedFallback = false;
        if (cpuResult.status === "rejected" || memResult.status === "rejected" || netResult.status === "rejected") {
          usedFallback = true;
          try {
            const metrics = await fetchLatestMetrics();
            // only fill in what the direct endpoints couldnt give us
            if (cpuResult.status === "rejected" && metrics.cpu) {
              setCpuData({
                container_id: "dsft-node-01",
                cpu_usage_percent: metrics.cpu.cpu_usage_percent,
                timestamp: metrics.cpu.timestamp,
              });
            } else if (cpuResult.status === "fulfilled") {
              setCpuData(cpuResult.value);
            }

            if (memResult.status === "rejected" && metrics.memory) {
              setMemData({
                container_id: "dsft-node-01",
                memory_used_mb: metrics.memory.memory_used_mb,
                memory_percent: metrics.memory.memory_percent,
                timestamp: metrics.memory.timestamp,
              });
            } else if (memResult.status === "fulfilled") {
              setMemData(memResult.value);
            }

            if (netResult.status === "rejected" && metrics.network) {
              setNetData({
                host: "10.0.0.1",
                pings: [],
                average_latency_ms: metrics.network.latency_ms,
                latency_quality: metrics.network.latency_ms > 100 ? "Poor" : metrics.network.latency_ms > 50 ? "Moderate" : "Good",
                jitter_ms: 0,
                jitter_quality: "N/A",
                container_id: "dsft-node-01",
                latency_ms: metrics.network.latency_ms,
                packet_loss_percent: metrics.network.packet_loss_percent,
                throughput_kbps: metrics.network.throughput_kbps,
                timestamp: metrics.network.timestamp,
              });
            } else if (netResult.status === "fulfilled") {
              setNetData(netResult.value);
            }
          } catch {
            // MetricsAPI also failed - fall back to mock for the failed ones
            if (cpuResult.status === "rejected") setCpuData(getMockCpuData());
            else setCpuData(cpuResult.value);
            if (memResult.status === "rejected") setMemData(getMockMemoryData());
            else setMemData(memResult.value);
            if (netResult.status === "rejected") setNetData(getMockNetworkData());
            else setNetData(netResult.value);
          }
        } else {
          // all direct endpoints worked fine
          setCpuData(cpuResult.value);
          setMemData(memResult.value);
          setNetData(netResult.value);
        }

        // health and status from the monitor (port 8000)
        setHealthData(healthResult.status === "fulfilled" ? healthResult.value : getMockHealthData());
        setStatusData(statusResult.status === "fulfilled" ? statusResult.value : getMockStatusData());

        // orchestrator state (port 8009) - its ok if this fails, just means orchestrator isnt up
        setOrchestratorState(orchResult.status === "fulfilled" ? orchResult.value : null);

        if (usedFallback) {
          addLog({
            timestamp: new Date().toISOString(),
            eventType: "metric_collected",
            message: "Some direct endpoints were down, used MetricsAPI as fallback",
          });
        }
      } else {
        // just generate some fake numbers
        setCpuData(getMockCpuData());
        setMemData(getMockMemoryData());
        setNetData(getMockNetworkData());
        setHealthData(getMockHealthData());
        setStatusData(getMockStatusData());
        setOrchestratorState(null);
      }
      setLastUpdate(new Date().toISOString());

      // log that we collected metrics
      addLog({
        timestamp: new Date().toISOString(),
        eventType: "metric_collected",
        message: `Metrics refreshed (${isLiveMode ? "live" : "mock"} mode)`,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(`Could not reach backend: ${msg}`);
      // if live mode fails, fall back to mock data so the dashboard still shows something
      setCpuData(getMockCpuData());
      setMemData(getMockMemoryData());
      setNetData(getMockNetworkData());
      setHealthData(getMockHealthData());
      setStatusData(getMockStatusData());
      setOrchestratorState(null);
      setLastUpdate(new Date().toISOString());

      addLog({
        timestamp: new Date().toISOString(),
        eventType: "error",
        message: `Failed to fetch live data: ${msg}. Falling back to mock.`,
      });
    }
  }, [isLiveMode, addLog]);

  // fetch data on mount and then every 5 seconds
  useEffect(() => {
    refreshData();
    const interval = setInterval(refreshData, 5000);
    return () => clearInterval(interval);
  }, [refreshData]);

  // figure out the status colors for each metric
  const cpuStatus = cpuData ? getStatusColor(cpuData.cpu_usage_percent, { warn: 60, danger: 80 }) : "good";
  const memStatus = memData ? getStatusColor(memData.memory_percent, { warn: 70, danger: 85 }) : "good";

  // for network, higher latency = worse
  const netLatency = netData?.average_latency_ms ?? 0;
  const netStatus = netLatency > 100 ? "destructive" : netLatency > 50 ? "warning" : "good";

  const cpuColors = getStatusClasses(cpuStatus);
  const memColors = getStatusClasses(memStatus);
  const netColors = getStatusClasses(netStatus);

  return (
    <div className="space-y-6">
      {/* page header with the data mode toggle */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold" data-testid="text-dashboard-title">
            System Dashboard
          </h2>
          <p className="text-sm text-muted-foreground">
            Real-time monitoring of container metrics
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* toggle between mock and live data */}
          <div className="flex items-center gap-2">
            <Label htmlFor="live-toggle" className="text-sm">
              Mock Data
            </Label>
            <Switch
              id="live-toggle"
              checked={isLiveMode}
              onCheckedChange={setIsLiveMode}
              data-testid="switch-live-mode"
            />
            <Label htmlFor="live-toggle" className="text-sm">
              Live API
            </Label>
          </div>
          {/* show the current mode */}
          <Badge variant={isLiveMode ? "default" : "secondary"}>
            {isLiveMode ? "LIVE" : "MOCK"}
          </Badge>
        </div>
      </div>

      {/* error banner if the backend is unreachable */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-md p-3 text-sm text-red-400" data-testid="text-error-banner">
          {error}
        </div>
      )}

      {/* the three metric cards in a grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* --- CPU card --- */}
        <Card className={`border ${cpuColors.border}`} data-testid="card-cpu">
          <CardHeader className="flex flex-row items-center justify-between gap-1 space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">CPU Usage</CardTitle>
            <div className={`p-2 rounded-md ${cpuColors.bg}`}>
              <Cpu className={`h-4 w-4 ${cpuColors.text}`} />
            </div>
          </CardHeader>
          <CardContent>
            {cpuData ? (
              <div className="space-y-3">
                <div className="flex items-baseline gap-1">
                  <span className={`text-2xl font-bold ${cpuColors.text}`} data-testid="text-cpu-value">
                    {cpuData.cpu_usage_percent.toFixed(1)}%
                  </span>
                </div>
                {/* progress bar showing cpu usage */}
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${cpuColors.progress}`}
                    style={{ width: `${Math.min(cpuData.cpu_usage_percent, 100)}%` }}
                  />
                </div>
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>Container: {cpuData.container_id}</span>
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {formatTime(cpuData.timestamp)}
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Loading...</p>
            )}
          </CardContent>
        </Card>

        {/* --- Memory card --- */}
        <Card className={`border ${memColors.border}`} data-testid="card-memory">
          <CardHeader className="flex flex-row items-center justify-between gap-1 space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Memory Usage</CardTitle>
            <div className={`p-2 rounded-md ${memColors.bg}`}>
              <MemoryStick className={`h-4 w-4 ${memColors.text}`} />
            </div>
          </CardHeader>
          <CardContent>
            {memData ? (
              <div className="space-y-3">
                <div className="flex items-baseline gap-2">
                  <span className={`text-2xl font-bold ${memColors.text}`} data-testid="text-memory-value">
                    {memData.memory_used_mb.toFixed(0)} MB
                  </span>
                  <span className="text-sm text-muted-foreground">
                    ({memData.memory_percent.toFixed(1)}%)
                  </span>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${memColors.progress}`}
                    style={{ width: `${Math.min(memData.memory_percent, 100)}%` }}
                  />
                </div>
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>Container: {memData.container_id}</span>
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {formatTime(memData.timestamp)}
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Loading...</p>
            )}
          </CardContent>
        </Card>

        {/* --- Network card --- */}
        <Card className={`border ${netColors.border}`} data-testid="card-network">
          <CardHeader className="flex flex-row items-center justify-between gap-1 space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Network Status</CardTitle>
            <div className={`p-2 rounded-md ${netColors.bg}`}>
              <Wifi className={`h-4 w-4 ${netColors.text}`} />
            </div>
          </CardHeader>
          <CardContent>
            {netData ? (
              <div className="space-y-3">
                <div className="flex items-baseline gap-2">
                  <span className={`text-2xl font-bold ${netColors.text}`} data-testid="text-network-value">
                    {netData.average_latency_ms.toFixed(1)} ms
                  </span>
                  <Badge variant="outline" className="text-xs">
                    {netData.latency_quality}
                  </Badge>
                </div>
                {/* show a few extra network stats */}
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <p className="text-muted-foreground text-xs">Jitter</p>
                    <p className="font-medium">{netData.jitter_ms.toFixed(1)} ms</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs">Packet Loss</p>
                    <p className="font-medium">{netData.packet_loss_percent.toFixed(2)}%</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs">Throughput</p>
                    <p className="font-medium">{netData.throughput_kbps.toFixed(0)} kbps</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs">Pings</p>
                    <p className="font-medium">{Array.isArray(netData.pings) ? netData.pings.length : netData.pings}</p>
                  </div>
                </div>
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>Host: {netData.host}</span>
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {formatTime(netData.timestamp)}
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Loading...</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* --- system status section from ExperimentMonitor --- */}
      {statusData && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* system state card */}
          <Card data-testid="card-system-status">
            <CardHeader className="flex flex-row items-center justify-between gap-1 space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">System Status</CardTitle>
              <div className="p-2 rounded-md bg-muted">
                <Activity className="h-4 w-4" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <span className="text-lg font-bold capitalize">{statusData.state}</span>
                  {/* colored badge based on the machine state */}
                  <Badge
                    className={
                      statusData.state === "idle"
                        ? "bg-gray-500/10 text-gray-500 border-gray-500/20"
                        : statusData.state === "running"
                          ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20"
                          : statusData.state === "stopping"
                            ? "bg-yellow-500/10 text-yellow-500 border-yellow-500/20"
                            : "bg-blue-500/10 text-blue-500 border-blue-500/20"
                    }
                  >
                    {statusData.state}
                  </Badge>
                </div>
                {statusData.message && (
                  <p className="text-xs text-muted-foreground">{statusData.message}</p>
                )}
              </div>
            </CardContent>
          </Card>

          {/* services overview card */}
          <Card data-testid="card-services">
            <CardHeader className="flex flex-row items-center justify-between gap-1 space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Services</CardTitle>
              <div className="p-2 rounded-md bg-muted">
                <Server className="h-4 w-4" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <p className="text-muted-foreground text-xs">Online</p>
                    <p className="font-medium">
                      {statusData.summary.services_online} / {Object.keys(statusData.services).length}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs">Injection Services</p>
                    <p className="font-medium">{statusData.summary.injection_services_online}</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* orchestrator state from port 8009 - shows the experiment lifecycle state machine */}
      {orchestratorState && (
        <Card data-testid="card-orchestrator-state">
          <CardHeader className="flex flex-row items-center justify-between gap-1 space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Orchestrator</CardTitle>
            <div className="p-2 rounded-md bg-muted">
              <Activity className="h-4 w-4" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold capitalize">{orchestratorState.state}</span>
                <Badge
                  className={
                    orchestratorState.state === "idle"
                      ? "bg-gray-500/10 text-gray-500 border-gray-500/20"
                      : orchestratorState.state === "running"
                        ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20"
                        : orchestratorState.state === "stopping"
                          ? "bg-yellow-500/10 text-yellow-500 border-yellow-500/20"
                          : "bg-blue-500/10 text-blue-500 border-blue-500/20"
                  }
                >
                  {orchestratorState.state}
                </Badge>
              </div>
              {orchestratorState.active_experiment_id && (
                <p className="text-xs text-muted-foreground">
                  Active experiment: {orchestratorState.active_experiment_id}
                </p>
              )}
              <p className="text-xs text-muted-foreground">
                Updated: {formatTime(orchestratorState.timestamp)}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* show active experiments from the monitor if there are any */}
      {statusData?.active_experiments && statusData.active_experiments.length > 0 && (
        <Card data-testid="card-active-experiments">
          <CardHeader>
            <CardTitle className="text-sm font-medium">
              Active Experiments ({statusData.active_experiments.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {statusData.active_experiments.map((exp) => (
                <div
                  key={exp.experiment_id}
                  className="flex items-center justify-between p-2 rounded-md border bg-card text-sm"
                >
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-xs">{exp.type}</Badge>
                    <span className="font-medium">{exp.source}</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    {exp.intensity && <span>Intensity: {exp.intensity}</span>}
                    <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20">
                      {exp.state}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* last update time at the bottom */}
      {lastUpdate && (
        <p className="text-xs text-muted-foreground text-center" data-testid="text-last-update">
          Last updated: {formatTime(lastUpdate)} (refreshes every 5s)
        </p>
      )}
    </div>
  );
}

