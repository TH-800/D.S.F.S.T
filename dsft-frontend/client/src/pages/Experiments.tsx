// Experiments.tsx - where you configure and launch chaos experiments
// you pick what kind of failure to inject, set the params, and hit start
// it also shows a list of all the experiments youve run so far

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Play, Square, Cpu, Wifi, AlertTriangle } from "lucide-react";
import { useAppState, type Experiment } from "@/lib/store";
import {
  injectCpuStress,
  injectLatency,
  injectPacketLoss,
  resetCpu,
  resetNetwork,
} from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

// the different injection types we support
type InjectionType = "cpu" | "latency" | "packet_loss";

// helper to generate a simple id
function makeId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

// formats a date string into something nice
function formatTime(ts: string) {
  try {
    return new Date(ts).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

export default function Experiments() {
  const { experiments, addExperiment, updateExperiment, addLog, isLiveMode } = useAppState();
  const { toast } = useToast();

  // form state for the experiment configuration
  const [injectionType, setInjectionType] = useState<InjectionType>("cpu");
  const [cpuPercent, setCpuPercent] = useState(50);
  const [cpuDuration, setCpuDuration] = useState(30);
  const [latencyDelay, setLatencyDelay] = useState(100);
  const [packetLossPercent, setPacketLossPercent] = useState(10);
  const [isStarting, setIsStarting] = useState(false);

  // starts a new experiment based on the current form values
  async function handleStart() {
    setIsStarting(true);

    // build the experiment object
    const now = new Date().toISOString();
    let name = "";
    let params: Record<string, number> = {};

    if (injectionType === "cpu") {
      name = `CPU Stress - ${cpuPercent}%`;
      params = { cpuPercent, duration: cpuDuration };
    } else if (injectionType === "latency") {
      name = `Latency Injection - ${latencyDelay}ms`;
      params = { delayMs: latencyDelay };
    } else {
      name = `Packet Loss - ${packetLossPercent}%`;
      params = { lossPercent: packetLossPercent };
    }

    const exp: Experiment = {
      id: makeId(),
      name,
      type: injectionType,
      status: "running",
      params,
      startedAt: now,
    };

    // if we're in live mode, actually call the backend
    if (isLiveMode) {
      try {
        if (injectionType === "cpu") {
          await injectCpuStress(cpuPercent, cpuDuration);
        } else if (injectionType === "latency") {
          await injectLatency(latencyDelay);
        } else {
          await injectPacketLoss(packetLossPercent);
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        toast({
          title: "Injection failed",
          description: `Backend error: ${msg}. Experiment logged locally.`,
          variant: "destructive",
        });
        addLog({
          timestamp: now,
          eventType: "error",
          message: `Failed to inject on backend: ${msg}`,
        });
      }
    }

    // add to our local state regardless
    addExperiment(exp);
    addLog({
      timestamp: now,
      eventType: "injection_started",
      message: `Started experiment: ${name}`,
    });

    toast({ title: "Experiment started", description: name });
    setIsStarting(false);
  }

  // stops/resets a running experiment
  async function handleStop(exp: Experiment) {
    const now = new Date().toISOString();

    // if live mode, hit the reset endpoints
    if (isLiveMode) {
      try {
        if (exp.type === "cpu") {
          await resetCpu();
        } else {
          // both latency and packet loss use the network reset
          await resetNetwork();
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        toast({
          title: "Reset failed",
          description: `Backend error: ${msg}`,
          variant: "destructive",
        });
      }
    }

    // update the experiment status in our state
    updateExperiment(exp.id, { status: "stopped", stoppedAt: now });
    addLog({
      timestamp: now,
      eventType: "injection_stopped",
      message: `Stopped experiment: ${exp.name}`,
    });

    toast({ title: "Experiment stopped", description: exp.name });
  }

  // figure out the badge color based on experiment status
  function getStatusBadge(status: string) {
    switch (status) {
      case "running":
        return <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20">Running</Badge>;
      case "stopped":
        return <Badge className="bg-yellow-500/10 text-yellow-500 border-yellow-500/20">Stopped</Badge>;
      case "completed":
        return <Badge className="bg-blue-500/10 text-blue-500 border-blue-500/20">Completed</Badge>;
      default:
        return <Badge variant="secondary">{status}</Badge>;
    }
  }

  // icon for each injection type
  function getTypeIcon(type: string) {
    switch (type) {
      case "cpu":
        return <Cpu className="h-4 w-4" />;
      case "latency":
        return <Wifi className="h-4 w-4" />;
      case "packet_loss":
        return <AlertTriangle className="h-4 w-4" />;
      default:
        return null;
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold" data-testid="text-experiments-title">
          Failure Injection
        </h2>
        <p className="text-sm text-muted-foreground">
          Configure and run chaos experiments on the distributed system
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* --- experiment configuration panel --- */}
        <Card className="lg:col-span-1" data-testid="card-experiment-config">
          <CardHeader>
            <CardTitle className="text-sm font-medium">New Experiment</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* injection type dropdown */}
            <div className="space-y-2">
              <Label htmlFor="injection-type">Injection Type</Label>
              <Select
                value={injectionType}
                onValueChange={(v) => setInjectionType(v as InjectionType)}
              >
                <SelectTrigger id="injection-type" data-testid="select-injection-type">
                  <SelectValue placeholder="Select type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="cpu">CPU Stress</SelectItem>
                  <SelectItem value="latency">Network Latency</SelectItem>
                  <SelectItem value="packet_loss">Packet Loss</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* cpu-specific inputs */}
            {injectionType === "cpu" && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="cpu-percent">CPU Percent (1-65%)</Label>
                  <Input
                    id="cpu-percent"
                    type="number"
                    min={1}
                    max={65}
                    value={cpuPercent}
                    onChange={(e) => setCpuPercent(Number(e.target.value))}
                    data-testid="input-cpu-percent"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cpu-duration">Duration (seconds)</Label>
                  <Input
                    id="cpu-duration"
                    type="number"
                    min={1}
                    max={300}
                    value={cpuDuration}
                    onChange={(e) => setCpuDuration(Number(e.target.value))}
                    data-testid="input-cpu-duration"
                  />
                </div>
              </>
            )}

            {/* latency-specific input */}
            {injectionType === "latency" && (
              <div className="space-y-2">
                <Label htmlFor="latency-delay">Delay (0-500 ms)</Label>
                <Input
                  id="latency-delay"
                  type="number"
                  min={0}
                  max={500}
                  value={latencyDelay}
                  onChange={(e) => setLatencyDelay(Number(e.target.value))}
                  data-testid="input-latency-delay"
                />
              </div>
            )}

            {/* packet loss input */}
            {injectionType === "packet_loss" && (
              <div className="space-y-2">
                <Label htmlFor="packet-loss">Loss Percent (0-50%)</Label>
                <Input
                  id="packet-loss"
                  type="number"
                  min={0}
                  max={50}
                  value={packetLossPercent}
                  onChange={(e) => setPacketLossPercent(Number(e.target.value))}
                  data-testid="input-packet-loss"
                />
              </div>
            )}

            {/* start button */}
            <Button
              onClick={handleStart}
              disabled={isStarting}
              className="w-full"
              data-testid="button-start-experiment"
            >
              <Play className="h-4 w-4 mr-2" />
              {isStarting ? "Starting..." : "Start Experiment"}
            </Button>

            {/* show a note about the current data mode */}
            <p className="text-xs text-muted-foreground text-center">
              {isLiveMode
                ? "Will send injection command to backend"
                : "Running in mock mode (no backend calls)"}
            </p>
          </CardContent>
        </Card>

        {/* --- list of experiments --- */}
        <Card className="lg:col-span-2" data-testid="card-experiment-list">
          <CardHeader>
            <CardTitle className="text-sm font-medium">
              Recent Experiments ({experiments.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {experiments.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <p className="text-sm">No experiments yet</p>
                <p className="text-xs mt-1">
                  Configure and start an experiment from the panel on the left
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {experiments.map((exp) => (
                  <div
                    key={exp.id}
                    className="flex items-center justify-between gap-3 p-3 rounded-md border bg-card"
                    data-testid={`card-experiment-${exp.id}`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="p-2 rounded-md bg-muted">
                        {getTypeIcon(exp.type)}
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate">{exp.name}</p>
                        <p className="text-xs text-muted-foreground">
                          Started: {formatTime(exp.startedAt)}
                          {exp.stoppedAt && ` | Stopped: ${formatTime(exp.stoppedAt)}`}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {getStatusBadge(exp.status)}
                      {exp.status === "running" && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleStop(exp)}
                          data-testid={`button-stop-${exp.id}`}
                        >
                          <Square className="h-3 w-3 mr-1" />
                          Stop
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
