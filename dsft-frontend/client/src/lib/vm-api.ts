import type { LatestMetrics } from "./api";

export interface RegisteredVM {
  vm_id: string;
  name: string;
  base_url: string;
  is_local: boolean;
}
export interface VMMember {
  vm_id: string;
  vm_name: string;
  vm: RegisteredVM;
  experiment_id: string | null;
  status: string;
  error: string | null;
}
export interface ExperimentBatch {
  batch_id: string;
  name: string;
  failure_type: string;
  status: string;
  members: VMMember[];
  started_at: string;
  ended_at: string | null;
  launch_errors?: { vm_id: string; error: string }[];
}
export interface ScopedMetrics extends LatestMetrics {
  vm_id: string;
  vm_name: string;
}
async function request<T>(path: string, method = "GET", body?: unknown, signal?: AbortSignal): Promise<T> {
  const deadline = AbortSignal.timeout(method === "GET" ? 30000 : 120000);
  const response = await fetch(path, {
    method,
    signal: signal ? AbortSignal.any([signal, deadline]) : deadline,
    cache: "no-store",
    ...(body === undefined ? {} : {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const message = typeof detail === "string" ? detail :
      detail?.message ? detail.message + (detail.vms?.map((v: {error: string}) => ": " + v.error).join("; ") || "") :
      typeof data?.error === "string" ? data.error :
      "Request failed (HTTP " + response.status + ")";
    throw new Error(message);
  }
  if (data === null) throw new Error("The VM API returned an invalid response");
  return data as T;
}
export const fetchVMs = () => request<RegisteredVM[]>("/api/8009/vms");
export const registerVM = (name: string, base_url: string) =>
  request<RegisteredVM>("/api/8009/vms", "POST", { name, base_url });
export const removeVM = (id: string) =>
  request<{removed: boolean}>("/api/8009/vms/" + encodeURIComponent(id), "DELETE");
export async function fetchVmMetrics(id: string, signal?: AbortSignal): Promise<ScopedMetrics> {
  const data = await request<ScopedMetrics>("/api/8008/vms/" + encodeURIComponent(id) + "/metrics/latest", "GET", undefined, signal);
  if (data.vm_id !== id) throw new Error("The returned measurements belong to a different VM");
  return data;
}
export async function fetchVmBatches(): Promise<ExperimentBatch[]> {
  const [active, recent] = await Promise.all([
    request<ExperimentBatch[]>("/api/8009/experiment-batches?active_only=true&limit=50"),
    request<ExperimentBatch[]>("/api/8009/experiment-batches?limit=20"),
  ]);
  // Keep unfinished runs visible even after newer completed runs fill the history.
  const activeIds = new Set(active.map(batch => batch.batch_id));
  return active.concat(recent.filter(batch => !activeIds.has(batch.batch_id)));
}
export const launchVmExperiment = (body: {
  name: string;
  failure_type: "cpu" | "memory" | "latency" | "packet_loss";
  parameters: Record<string, number>;
  vm_ids: string[];
}) => request<ExperimentBatch>("/api/8009/experiments/launch", "POST", body);
export const stopVmBatch = (id: string) =>
  request<ExperimentBatch>("/api/8009/experiment-batches/" + encodeURIComponent(id) + "/stop", "POST");
export const stopAllVmBatches = () =>
  request<{status: string}>("/api/8009/experiment-batches/emergency-stop", "POST");
