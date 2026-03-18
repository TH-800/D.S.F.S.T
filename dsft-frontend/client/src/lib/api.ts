// api.ts - handles all the communication with our FastAPI backend scripts
// each backend script runs on its own port using FastAPI dev mode
// the ports are assigned like this:
//   - BasenetworkInfo.py (network monitoring) -> port 8001
//   - LinuxCpuStatus.py (cpu monitoring) -> port 8002
//   - LinuxMemoryStatus.py (memory monitoring) -> port 8003
//   - CPUstressInjection.py (cpu stress injection) -> port 8004
//   - NetworkLatencyInjection.py (latency injection) -> port 8005
//   - PacketLossInjection.py (packet loss injection) -> port 8006
// when the backend scripts arent running we fall back to mock data so the demo still works

// base host for all the FastAPI scripts - they all run on the same machine just different ports
// change this if the backend is on a different machine (e.g. a VM or remote server)
const BACKEND_HOST = "http://localhost";

// port assignments for each backend script
// these match the --port flags used when starting each script with fastapi dev
const PORTS = {
  network: 8001,    // BasenetworkInfo.py --port 8001
  cpu: 8002,        // LinuxCpuStatus.py --port 8002
  memory: 8003,     // LinuxMemoryStatus.py --port 8003
  cpuInject: 8004,  // CPUstressInjection.py --port 8004
  latencyInject: 8005, // NetworkLatencyInjection.py --port 8005
  packetLossInject: 8006, // PacketLossInjection.py --port 8006
} as const;

// helper to build the full URL for a given service
// e.g. getUrl("cpu") returns "http://localhost:8002"
function getUrl(service: keyof typeof PORTS): string {
  return `${BACKEND_HOST}:${PORTS[service]}`;
}

// --- types for the data we get back from the API ---

// what we get from /cpu
export interface CpuData {
  container_id: string;
  cpu_usage_percent: number;
  timestamp: string;
}

// what we get from /memory
export interface MemoryData {
  container_id: string;
  memory_used_mb: number;
  memory_percent: number;
  timestamp: string;
}

// what we get from /network
export interface NetworkData {
  host: string;
  pings: number[];
  average_latency_ms: number;
  latency_quality: string;
  jitter_ms: number;
  jitter_quality: string;
  container_id: string;
  latency_ms: number;
  packet_loss_percent: number;
  throughput_kbps: number;
  timestamp: string;
}

// --- mock data generators ---
// these make the numbers slightly different each time so it looks like real monitoring

function randomBetween(min: number, max: number): number {
  return Math.round((Math.random() * (max - min) + min) * 100) / 100;
}

function getCurrentTimestamp(): string {
  return new Date().toISOString();
}

// generates fake CPU data that looks realistic
export function getMockCpuData(): CpuData {
  return {
    container_id: "dsft-node-01",
    cpu_usage_percent: randomBetween(35, 45),
    timestamp: getCurrentTimestamp(),
  };
}

// generates fake memory data
export function getMockMemoryData(): MemoryData {
  const used = randomBetween(2100, 2400);
  // total memory is 4096MB so we can calc the percent
  const percent = Math.round((used / 4096) * 100 * 10) / 10;
  return {
    container_id: "dsft-node-01",
    memory_used_mb: used,
    memory_percent: percent,
    timestamp: getCurrentTimestamp(),
  };
}

// generates fake network data
export function getMockNetworkData(): NetworkData {
  const latency = randomBetween(15, 25);
  const jitter = randomBetween(3, 8);
  
  // figure out quality labels based on the numbers
  let latencyQuality = "Good";
  if (latency > 100) latencyQuality = "Poor";
  else if (latency > 50) latencyQuality = "Moderate";

  let jitterQuality = "Good";
  if (jitter > 15) jitterQuality = "Poor";
  else if (jitter > 10) jitterQuality = "Moderate";

  return {
    host: "10.0.0.1",
    pings: [latency + randomBetween(-3, 3), latency + randomBetween(-3, 3), latency + randomBetween(-3, 3), latency + randomBetween(-3, 3), latency + randomBetween(-3, 3)],
    average_latency_ms: latency,
    latency_quality: latencyQuality,
    jitter_ms: jitter,
    jitter_quality: jitterQuality,
    container_id: "dsft-node-01",
    latency_ms: latency,
    packet_loss_percent: randomBetween(0, 0.5),
    throughput_kbps: randomBetween(900, 1100),
    timestamp: getCurrentTimestamp(),
  };
}

// --- actual API calls to the FastAPI backend scripts ---
// each function hits the correct port for the script that handles that endpoint

// fetches real cpu data from LinuxCpuStatus.py running on port 8002
export async function fetchCpuData(): Promise<CpuData> {
  const res = await fetch(`${getUrl("cpu")}/cpu`);
  if (!res.ok) throw new Error("Failed to fetch CPU data");
  return res.json();
}

// fetches real memory data from LinuxMemoryStatus.py running on port 8003
export async function fetchMemoryData(): Promise<MemoryData> {
  const res = await fetch(`${getUrl("memory")}/memory`);
  if (!res.ok) throw new Error("Failed to fetch memory data");
  return res.json();
}

// fetches real network data from BasenetworkInfo.py running on port 8001
export async function fetchNetworkData(): Promise<NetworkData> {
  const res = await fetch(`${getUrl("network")}/network`);
  if (!res.ok) throw new Error("Failed to fetch network data");
  return res.json();
}

// --- injection endpoints (POST requests to start chaos experiments) ---
// each injection script runs on its own port so we hit the right one

// sends a cpu stress injection request to CPUstressInjection.py on port 8004
export async function injectCpuStress(cpuPercent: number, duration: number) {
  const res = await fetch(
    `${getUrl("cpuInject")}/inject/cpu?cpu_percent=${cpuPercent}&duration=${duration}`,
    { method: "POST" }
  );
  if (!res.ok) throw new Error("Failed to inject CPU stress");
  return res.json();
}

// sends a latency injection request to NetworkLatencyInjection.py on port 8005
export async function injectLatency(delayMs: number) {
  const res = await fetch(`${getUrl("latencyInject")}/inject/latency/${delayMs}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to inject latency");
  return res.json();
}

// sends a packet loss injection request to PacketLossInjection.py on port 8006
export async function injectPacketLoss(lossPercent: number) {
  const res = await fetch(`${getUrl("packetLossInject")}/inject/packetloss/${lossPercent}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to inject packet loss");
  return res.json();
}

// --- reset endpoints ---
// resets go to the same script that started the injection

// resets cpu stress by calling the reset endpoint on CPUstressInjection.py (port 8004)
export async function resetCpu() {
  const res = await fetch(`${getUrl("cpuInject")}/reset/cpu`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to reset CPU");
  return res.json();
}

// resets network conditions - this can go to either the latency or packet loss script
// since both have a /reset/network endpoint, we use the latency one (port 8005)
export async function resetNetwork() {
  const res = await fetch(`${getUrl("latencyInject")}/reset/network`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to reset network");
  return res.json();
}

