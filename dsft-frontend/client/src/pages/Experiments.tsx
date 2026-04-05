// Experiments.tsx - where you configure and launch chaos experiments
// you pick what kind of failure to inject, set the params, and hit start
// it also shows a list of all the experiments youve run so far

import { useState, useEffect, useRef, useCallback } from "react";
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
import { Play, Square, Cpu, Wifi, AlertTriangle, MemoryStick, OctagonX } from "lucide-react";
import { useAppState, type Experiment } from "@/lib/store";
import {
  injectCpuStress,
  injectLatency,
  injectPacketLoss,
  injectMemoryStress,
  resetCpu,
  resetNetwork,
  resetMemory,
  fetchDbExperiments,
  fetchOrchestratorState,
  createExperiment,
  startExperiment,
  stopExperiment,
  emergencyStop,
  type OrchestratorState,
  type DbExperiment,
} from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

// the different injection types we support (now includes memory stress)
type InjectionType = "cpu" | "latency" | "packet_loss" | "memory";

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
  const [memoryMb, setMemoryMb] = useState(512);
  const [memoryDuration, setMemoryDuration] = useState(30);
  const [isStarting, setIsStarting] = useState(false);

  // orchestrator state from port 8009 and experiments from the database
  const [orchestratorState, setOrchestratorState] = useState<OrchestratorState | null>(null);
  const [dbExperiments, setDbExperiments] = useState<DbExperiment[]>([]);
  const [isStopping, setIsStopping] = useState(false);

  // keeps track of auto-complete timers so we can cancel them if the user stops early
  // key = experiment id, value = the timeout handle
  const autoCompleteTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // fetch experiments from the database and orchestrator state when in live mode
  const refreshFromBackend = useCallback(async () => {
    if (!isLiveMode) return;
    try {
      const [orchState, dbExps] = await Promise.allSettled([
        fetchOrchestratorState(),
        fetchDbExperiments(50),
      ]);
      if (orchState.status === "fulfilled") setOrchestratorState(orchState.value);
      if (dbExps.status === "fulfilled") {
        const fetchedDbExps = dbExps.value;
        setDbExperiments(fetchedDbExps);

        // sync local experiment statuses with what the database says
        // this handles the case where stress-ng finishes and the DB is updated
        // but the local React state still shows "Running"
        fetchedDbExps.forEach((dbExp) => {
          const localExp = experiments.find((e) => e.id === dbExp.experiment_id);
          if (localExp && localExp.status === "running" &&
              (dbExp.status === "completed" || dbExp.status === "stopped")) {
            const endedAt = dbExp.ended_at || new Date().toISOString();
            updateExperiment(localExp.id, {
              status: dbExp.status as "completed" | "stopped",
              stoppedAt: endedAt,
            });
          }
        });
      }
    } catch {
      // silently fail - the orchestrator or db might not be running
    }
  }, [isLiveMode, experiments, updateExperiment]);

  // on mount and when live mode changes, pull from the backend
  useEffect(() => {
    refreshFromBackend();
    // poll every 10 seconds to keep the orchestrator state fresh
    if (isLiveMode) {
      const interval = setInterval(refreshFromBackend, 10000);
      return () => clearInterval(interval);
    }
  }, [refreshFromBackend, isLiveMode]);

  // cleanup all timers when the component unmounts so we dont leak memory
  useEffect(() => {
    return () => {
      Object.values(autoCompleteTimers.current).forEach(clearTimeout);
    };
  }, []);

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
    } else if (injectionType === "packet_loss") {
      name = `Packet Loss - ${packetLossPercent}%`;
      params = { lossPercent: packetLossPercent };
    } else if (injectionType === "memory") {
      name = `Memory Stress - ${memoryMb}MB`;
      params = { memoryMb, duration: memoryDuration };
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
    // first try the orchestrator (port 8009) which handles the full lifecycle
    // if that fails, fall back to calling the injection scripts directly
    if (isLiveMode) {
      let orchestratorWorked = false;
      try {
        // try orchestrator first - it creates the experiment in the database and
        // coordinates the injection through the proper state machine
        const created = await createExperiment({
          name,
          failure_type: injectionType,
          parameters: params,
        });
        const started = await startExperiment(created.experiment_id, params);
        // use the orchestrator's experiment id so we can track it later
        exp.id = created.experiment_id;
        orchestratorWorked = true;

        addLog({
          timestamp: now,
          eventType: "injection_started",
          message: `Orchestrator started experiment: ${name} (id: ${created.experiment_id})`,
        });

        // refresh to pick up the new orchestrator state
        refreshFromBackend();
      } catch (orchErr) {
        // orchestrator is unreachable - fall back to direct injection
        const orchMsg = orchErr instanceof Error ? orchErr.message : "Unknown error";
        addLog({
          timestamp: now,
          eventType: "error",
          message: `Orchestrator unreachable (${orchMsg}), falling back to direct injection`,
        });

        try {
          let result: any;
          if (injectionType === "cpu") {
            result = await injectCpuStress(cpuPercent, cpuDuration);
          } else if (injectionType === "latency") {
            result = await injectLatency(latencyDelay);
          } else if (injectionType === "packet_loss") {
            result = await injectPacketLoss(packetLossPercent);
          } else if (injectionType === "memory") {
            result = await injectMemoryStress(memoryMb, memoryDuration);
          }
          // check if backend returned an error (e.g. "CPU stress already running")
          // the backend returns { error: "..." } with a 200 status, not a thrown error
          if (result && result.error) {
            toast({
              title: "Cannot start experiment",
              description: result.error,
              variant: "destructive",
            });
            setIsStarting(false);
            return;
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
    }

    // add to our local state regardless
    addExperiment(exp);
    addLog({
      timestamp: now,
      eventType: "injection_started",
      message: `Started experiment: ${name}`,
    });

    // if the experiment has a duration, set a timer to auto-complete it
    // this way the frontend knows when stress-ng finishes on the backend
    // without the user having to manually click stop
    const duration = params.duration;
    if (duration && duration > 0) {
      const timerId = setTimeout(() => {
        const completedAt = new Date().toISOString();
        updateExperiment(exp.id, { status: "completed", stoppedAt: completedAt });
        addLog({
          timestamp: completedAt,
          eventType: "injection_stopped",
          message: `Experiment auto-completed after ${duration}s: ${name}`,
        });
        // clean up the timer reference
        delete autoCompleteTimers.current[exp.id];
      }, duration * 1000); // convert seconds to milliseconds

      autoCompleteTimers.current[exp.id] = timerId;
    }

    toast({ title: "Experiment started", description: name });
    setIsStarting(false);
  }

  // stops/resets a running experiment
  // tries the orchestrator first, then falls back to direct reset calls
  async function handleStop(exp: Experiment) {
    const now = new Date().toISOString();

    // if live mode, try orchestrator stop first, then fall back to direct resets
    if (isLiveMode) {
      let orchestratorWorked = false;
      try {
        await stopExperiment(exp.id);
        orchestratorWorked = true;
        refreshFromBackend();
      } catch {
        // orchestrator didnt work, fall back to the direct reset endpoints
      }

      if (!orchestratorWorked) {
        try {
          if (exp.type === "cpu") {
            await resetCpu();
          } else if (exp.type === "memory") {
            await resetMemory();
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
    }

    // if there was an auto-complete timer running for this experiment, cancel it
    // since the user manually stopped it before the duration ran out
    if (autoCompleteTimers.current[exp.id]) {
      clearTimeout(autoCompleteTimers.current[exp.id]);
      delete autoCompleteTimers.current[exp.id];
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

  // emergency stop - kills ALL running injections immediately
  // this is the panic button, it tells the orchestrator to shut everything down
  async function handleEmergencyStop() {
    setIsStopping(true);
    const now = new Date().toISOString();
    try {
      const result = await emergencyStop();
      toast({
        title: "Emergency stop executed",
        description: result.note || "All injections have been stopped",
      });
      addLog({
        timestamp: now,
        eventType: "injection_stopped",
        message: `Emergency stop: ${result.note || "all injections halted"}`,
      });
      // mark all running local experiments as stopped
      experiments
        .filter((e) => e.status === "running")
        .forEach((e) => {
          updateExperiment(e.id, { status: "stopped", stoppedAt: now });
          // cancel any auto-complete timers
          if (autoCompleteTimers.current[e.id]) {
            clearTimeout(autoCompleteTimers.current[e.id]);
            delete autoCompleteTimers.current[e.id];
          }
        });
      refreshFromBackend();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      toast({
        title: "Emergency stop failed",
        description: `Could not reach orchestrator: ${msg}`,
        variant: "destructive",
      });
    }
    setIsStopping(false);
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
      case "memory":
        return <MemoryStick className="h-4 w-4" />;
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

      {/* orchestrator state and emergency stop - only shown in live mode when orchestrator is reachable */}
      {isLiveMode && orchestratorState && (
        <Card data-testid="card-orchestrator-status">
          <CardContent className="py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-sm text-muted-foreground">Orchestrator:</span>
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
                {orchestratorState.active_experiment_id && (
                  <span className="text-xs text-muted-foreground">
                    Active: {orchestratorState.active_experiment_id}
                  </span>
                )}
              </div>
              {/* the big red button - emergency stop kills everything */}
              <Button
                variant="destructive"
                size="sm"
                onClick={handleEmergencyStop}
                disabled={isStopping}
                data-testid="button-emergency-stop"
              >
                <OctagonX className="h-4 w-4 mr-1" />
                {isStopping ? "Stopping..." : "Emergency Stop"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

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
                  <SelectItem value="memory">Memory Stress</SelectItem>
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

            {/* memory-specific inputs */}
            {injectionType === "memory" && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="memory-mb">Memory (64-4096 MB)</Label>
                  <Input
                    id="memory-mb"
                    type="number"
                    min={64}
                    max={4096}
                    value={memoryMb}
                    onChange={(e) => setMemoryMb(Number(e.target.value))}
                    data-testid="input-memory-mb"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="memory-duration">Duration (seconds)</Label>
                  <Input
                    id="memory-duration"
                    type="number"
                    min={1}
                    max={300}
                    value={memoryDuration}
                    onChange={(e) => setMemoryDuration(Number(e.target.value))}
                    data-testid="input-memory-duration"
                  />
                </div>
              </>
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
        {/* in live mode we merge local experiments with ones from the database */}
        <Card className="lg:col-span-2" data-testid="card-experiment-list">
          <CardHeader>
            <CardTitle className="text-sm font-medium">
              Recent Experiments ({experiments.length}{isLiveMode && dbExperiments.length > 0 ? ` + ${dbExperiments.length} from database` : ""})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {experiments.length === 0 && dbExperiments.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <p className="text-sm">No experiments yet</p>
                <p className="text-xs mt-1">
                  Configure and start an experiment from the panel on the left
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {/* local experiments from the current session */}
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

                {/* experiments from the database - shown in live mode */}
                {/* we filter out any that are already in the local list to avoid duplicates */}
                {isLiveMode && dbExperiments
                  .filter((dbExp) => !experiments.some((e) => e.id === dbExp.experiment_id))
                  .map((dbExp) => (
                    <div
                      key={dbExp.experiment_id}
                      className="flex items-center justify-between gap-3 p-3 rounded-md border bg-card/50"
                      data-testid={`card-db-experiment-${dbExp.experiment_id}`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="p-2 rounded-md bg-muted">
                          {getTypeIcon(dbExp.failure_type)}
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-medium truncate">{dbExp.name}</p>
                          <p className="text-xs text-muted-foreground">
                            Started: {formatTime(dbExp.started_at)}
                            {dbExp.ended_at && ` | Ended: ${formatTime(dbExp.ended_at)}`}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {getStatusBadge(dbExp.status)}
                        <Badge variant="outline" className="text-xs">DB</Badge>
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
