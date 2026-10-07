import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  fetchVMs, registerVM, removeVM, fetchVmMetrics, fetchVmBatches,
  launchVmExperiment, stopVmBatch, stopAllVmBatches,
  type RegisteredVM, type ExperimentBatch, type ScopedMetrics,
} from "@/lib/vm-api";

const active = ["starting", "running", "stopping", "partial_failure"];
const limits = {
  cpu: { label: "CPU percent", field: "cpu_percent", min: 1, max: 65, initial: 10 },
  memory: { label: "Memory MB", field: "memory_mb", min: 64, max: 4096, initial: 128 },
  latency: { label: "Latency ms", field: "latency_ms", min: 0, max: 500, initial: 100 },
  packet_loss: { label: "Packet loss percent", field: "packet_loss_percent", min: 0, max: 50, initial: 10 },
};
type FailureType = keyof typeof limits;
const selectStyle = "h-10 w-full rounded-md border bg-background px-3 text-sm";
function message(error: unknown) {
  return error instanceof Error ? error.message : "The request failed";
}
function value(value: number | undefined, suffix: string) {
  return value === undefined ? "Unavailable" : value.toFixed(1) + suffix;
}

export default function VMs() {
  const [vms, setVms] = useState<RegisteredVM[]>([]);
  const [batches, setBatches] = useState<ExperimentBatch[]>([]);
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [metricVm, setMetricVm] = useState("local");
  const [metrics, setMetrics] = useState<ScopedMetrics | null>(null);
  const [metricsError, setMetricsError] = useState("");
  const [selected, setSelected] = useState<string[]>(["local"]);
  const [type, setType] = useState<FailureType>("cpu");
  const [amount, setAmount] = useState(10);
  const [duration, setDuration] = useState(15);
  const [error, setError] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [known, runs] = await Promise.allSettled([fetchVMs(), fetchVmBatches()]);
    if (known.status === "fulfilled") {
      setVms(known.value);
      setSelected(old => old.filter(id => known.value.some(vm => vm.vm_id === id)));
      setMetricVm(old => known.value.some(vm => vm.vm_id === old) ? old : "local");
    }
    if (runs.status === "fulfilled") setBatches(runs.value);
    const failure = known.status === "rejected" ? known.reason :
      runs.status === "rejected" ? runs.reason : null;
    setConnectionError(failure ? message(failure) : "");
  }, []);
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    let cancelled = false;
    setMetrics(null);
    setMetricsError("");
    const poll = async () => {
      try {
        const data = await fetchVmMetrics(metricVm);
        if (!cancelled) { setMetrics(data); setMetricsError(""); }
      } catch (error) {
        if (!cancelled) { setMetrics(null); setMetricsError(message(error)); }
      }
    };
    void poll();
    const timer = setInterval(() => void poll(), 5000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [metricVm]);

  async function action(operation: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try { await operation(); }
    catch (error) { setError(message(error)); }
    finally { await refresh(); setBusy(false); }
  }
  function add(event: FormEvent) {
    event.preventDefault();
    void action(async () => {
      await registerVM(name, address);
      setName(""); setAddress("");
    });
  }
  function launch(event: FormEvent) {
    event.preventDefault();
    const parameters: Record<string, number> = { [limits[type].field]: amount };
    if (type === "cpu" || type === "memory") parameters.duration_seconds = duration;
    void action(async () => {
      const batch = await launchVmExperiment({
        name: type + " on " + selected.length + " VM(s)",
        failure_type: type, parameters, vm_ids: selected,
      });
      if (batch.status !== "running")
        throw new Error("Launch " + batch.status + ". Inspect the per-VM results below.");
    });
  }

  return <div className="space-y-6">
    <div>
      <h2 className="text-xl font-bold">Virtual machines</h2>
      <p className="text-sm text-muted-foreground">
        Register VM API addresses, inspect stored measurements and run one experiment across selected VMs.
      </p>
    </div>
    {(error || connectionError) && <p role="alert" className="text-sm text-destructive">{error || connectionError}</p>}
    <Card><CardHeader><CardTitle>Known VMs</CardTitle></CardHeader><CardContent className="space-y-4">
      <form onSubmit={add} className="flex flex-wrap gap-3 items-end">
        <div><Label htmlFor="vm-name">VM name</Label><Input id="vm-name" value={name} maxLength={80} required onChange={e => setName(e.target.value)} /></div>
        <div className="flex-1 min-w-56"><Label htmlFor="vm-address">API address</Label><Input id="vm-address" type="url" placeholder="http://192.168.56.11:3000" value={address} required onChange={e => setAddress(e.target.value)} /></div>
        <Button disabled={busy}>Register VM</Button>
      </form>
      {vms.map(vm => <div key={vm.vm_id} className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
        <div><span className="font-medium">{vm.name}</span> {vm.is_local && <Badge variant="secondary">Local</Badge>}<p className="text-sm text-muted-foreground">{vm.base_url}</p></div>
        {!vm.is_local && <Button variant="outline" disabled={busy} onClick={() => void action(() => removeVM(vm.vm_id))}>Remove</Button>}
      </div>)}
      <p className="text-xs text-muted-foreground">Removing a registration leaves the VM and its data intact. Active batches must finish or stop first.</p>
    </CardContent></Card>
    <Card><CardHeader><CardTitle>VM measurements</CardTitle></CardHeader><CardContent className="space-y-4">
      <Label htmlFor="metrics-vm">VM</Label>
      <select id="metrics-vm" className={selectStyle} value={metricVm} onChange={e => setMetricVm(e.target.value)}>
        {vms.map(vm => <option key={vm.vm_id} value={vm.vm_id}>{vm.name}</option>)}
      </select>
      {metricsError && <p role="alert" className="text-sm text-destructive">{metricsError}</p>}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div><p className="text-sm text-muted-foreground">CPU</p><p className="text-xl">{value(metrics?.cpu?.cpu_usage_percent, "%")}</p><p className="text-xs">{metrics?.cpu?.timestamp}</p></div>
        <div><p className="text-sm text-muted-foreground">Memory</p><p className="text-xl">{value(metrics?.memory?.memory_percent, "%")}</p><p className="text-xs">{metrics?.memory?.timestamp}</p></div>
        <div><p className="text-sm text-muted-foreground">Network latency / packet loss</p><p className="text-xl">{value(metrics?.network?.latency_ms, " ms")} / {value(metrics?.network?.packet_loss_percent, "%")}</p><p className="text-xs">Throughput: {value(metrics?.network?.throughput_kbps, " kbps")}</p><p className="text-xs">{metrics?.network?.timestamp}</p></div>
      </div>
      <p className="text-xs text-muted-foreground">Actual stored readings from the selected VM, refreshed every five seconds.</p>
    </CardContent></Card>
    <Card><CardHeader><CardTitle>Launch on selected VMs</CardTitle></CardHeader><CardContent>
      <form onSubmit={launch} className="space-y-4">
        <fieldset className="flex flex-wrap gap-4"><legend className="text-sm mb-2">Targets</legend>
          {vms.map(vm => <label key={vm.vm_id} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={selected.includes(vm.vm_id)} onChange={e => setSelected(old => e.target.checked ? [...old, vm.vm_id] : old.filter(id => id !== vm.vm_id))} />{vm.name}
          </label>)}
        </fieldset>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div><Label htmlFor="batch-type">Failure type</Label><select id="batch-type" className={selectStyle} value={type} onChange={e => { const next = e.target.value as FailureType; setType(next); setAmount(limits[next].initial); }}>
            <option value="cpu">CPU</option><option value="memory">Memory</option><option value="latency">Latency</option><option value="packet_loss">Packet loss</option>
          </select></div>
          <div><Label htmlFor="batch-amount">{limits[type].label}</Label><Input id="batch-amount" type="number" required step={1} min={limits[type].min} max={limits[type].max} value={amount} onChange={e => setAmount(Number(e.target.value))} /></div>
          {(type === "cpu" || type === "memory") && <div><Label htmlFor="batch-duration">Duration seconds</Label><Input id="batch-duration" type="number" min={1} max={300} step={1} required value={duration} onChange={e => setDuration(Number(e.target.value))} /></div>}
        </div>
        <Button disabled={busy || selected.length === 0}>{busy ? "Working..." : "Launch experiment"}</Button>
        <p className="text-xs text-muted-foreground">Targets must be idle. If a launch fails, the coordinator attempts to stop every child it created and reports any unconfirmed reset.</p>
      </form>
    </CardContent></Card>
    <Card><CardHeader><CardTitle>Multi-VM batches</CardTitle></CardHeader><CardContent className="space-y-4">
      <Button variant="destructive" disabled={busy || !batches.some(b => active.includes(b.status))} onClick={() => void action(async () => {
        const result = await stopAllVmBatches();
        if (result.status !== "stopped") throw new Error("Some batches still need attention. Inspect their results.");
      })}>Stop active batches</Button>
      {batches.length === 0 && <p className="text-sm text-muted-foreground">No batches yet.</p>}
      {batches.map(batch => <div key={batch.batch_id} className="border-t pt-4 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-medium">{batch.name} <Badge variant="secondary">{batch.status}</Badge></span>
          {active.includes(batch.status) && <Button variant="outline" disabled={busy || ["starting", "stopping"].includes(batch.status)} onClick={() => void action(async () => {
            const result = await stopVmBatch(batch.batch_id);
            if (active.includes(result.status)) throw new Error("Some child resets are unconfirmed. Inspect the VM results.");
          })}>Stop batch</Button>}
        </div>
        {batch.launch_errors?.map((item, index) => <p key={index} className="text-sm text-destructive">Launch: {item.error}</p>)}
        {batch.members.map(member => <div key={member.vm_id} className="text-sm">
          <span>{member.vm_name}: {member.status}</span>
          {member.error && <span className="text-destructive"> - {member.error}</span>}
          {member.experiment_id && <a className="ml-3 underline" target="_blank" rel="noreferrer" href={(member.vm.is_local ? "" : member.vm.base_url) + "/api/8008/experiments/" + encodeURIComponent(member.experiment_id) + "/report"}>Report JSON</a>}
        </div>)}
      </div>)}
    </CardContent></Card>
  </div>;
}
