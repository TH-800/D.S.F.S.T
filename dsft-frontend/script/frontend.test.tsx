import assert from "node:assert/strict";
import { test } from "node:test";
import { act, type ReactNode } from "react";

// Load React DOM after installing the browser globals, including input events.
const { createRoot } = await import("react-dom/client");
const { default: ServiceStatusIndicator } = await import("../client/src/components/ServiceStatusIndicator");
const { default: VMs } = await import("../client/src/pages/VMs");
const { default: Dashboard } = await import("../client/src/pages/Dashboard");
const { AppProvider } = await import("../client/src/lib/store");

function mount() {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  return {
    container,
    render: (element: ReactNode) => act(async () => { root.render(element); }),
    close: async () => { await act(async () => root.unmount()); container.remove(); },
  };
}
const reply = (data: unknown, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { "content-type": "application/json" },
});
const health = { status: "ok", service: "ExperimentMonitor", timestamp: "2026-10-15T12:00:00Z" };

test("mock status makes no health requests; the dashboard includes the indicator", async () => {
  const view = mount();
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => { calls++; throw new Error("Unexpected request in mock mode"); };
  try {
    await view.render(<ServiceStatusIndicator isLiveMode={false} />);
    assert.equal(view.container.textContent, "Monitor simulated");
    await view.render(<AppProvider><Dashboard /></AppProvider>);
    assert.equal(view.container.querySelector('[data-testid="monitor-health"]')?.textContent, "Monitor simulated");
    assert.equal(calls, 0);
  } finally { await view.close(); globalThis.fetch = original; }
});

test("health indicator checks the health endpoint, detects failure, and recovers", async () => {
  const view = mount();
  const originalFetch = globalThis.fetch;
  const originalTimeout = globalThis.setTimeout;
  const timers: ReturnType<typeof setTimeout>[] = [];
  let nextPoll: (() => Promise<void>) | undefined;
  let response = () => reply(health);
  const calls: { url: string; options?: RequestInit }[] = [];
  globalThis.setTimeout = ((callback: () => Promise<void>, delay: number, ...args: any[]) => {
    if (delay === 5000) {
      nextPoll = callback;
      const timer = originalTimeout(() => {}, 60000);
      timers.push(timer);
      return timer;
    }
    return originalTimeout(callback, delay, ...args);
  }) as typeof setTimeout;
  globalThis.fetch = async (url, options) => { calls.push({ url: String(url), options }); return response(); };
  async function poll() {
    const callback = nextPoll;
    assert.ok(callback, "a completed check schedules the next check");
    nextPoll = undefined;
    await act(callback);
  }
  try {
    await view.render(<ServiceStatusIndicator isLiveMode />);
    assert.equal(view.container.textContent, "Monitor online");
    assert.equal(calls[0].url, "/api/8000/health");
    assert.equal(calls[0].options?.cache, "no-store");
    assert.ok(calls[0].options?.signal);
    response = () => reply({ status: "error" }, 503);
    await poll();
    assert.equal(view.container.textContent, "Monitor offline");
    response = () => { throw new Error("Connection refused"); };
    await poll();
    assert.equal(view.container.textContent, "Monitor offline");
    response = () => reply({ status: "error", service: "ExperimentMonitor" });
    await poll();
    assert.equal(view.container.textContent, "Monitor offline", "HTTP 200 with unhealthy content is not online");
    response = () => reply({ ...health, service: "wrong-service" });
    await poll();
    assert.equal(view.container.textContent, "Monitor offline");
    response = () => reply(health);
    await poll();
    assert.equal(view.container.textContent, "Monitor online");
    assert.ok(calls.every(call => call.url === "/api/8000/health"));
  } finally {
    await view.close();
    timers.forEach(clearTimeout);
    globalThis.fetch = originalFetch;
    globalThis.setTimeout = originalTimeout;
  }
});

test("pending health checks time out and are cancelled when changing mode or leaving", async () => {
  const view = mount();
  const originalFetch = globalThis.fetch;
  const originalTimeout = AbortSignal.timeout;
  let deadline = new AbortController();
  const signals: AbortSignal[] = [];
  AbortSignal.timeout = (milliseconds) => { assert.equal(milliseconds, 8000); return deadline.signal; };
  globalThis.fetch = async (_url, options) => new Promise<Response>((_resolve, reject) => {
    const signal = options!.signal!;
    signals.push(signal);
    signal.addEventListener("abort", () => reject(signal.reason), { once: true });
  });
  try {
    await view.render(<ServiceStatusIndicator isLiveMode />);
    assert.equal(view.container.textContent, "Checking monitor");
    await act(async () => deadline.abort(new Error("Timed out")));
    assert.equal(view.container.textContent, "Monitor offline");
    await view.render(<ServiceStatusIndicator isLiveMode={false} />);
    deadline = new AbortController();
    await view.render(<ServiceStatusIndicator isLiveMode />);
    assert.equal(view.container.textContent, "Checking monitor", "live mode starts with a fresh check");
    await view.render(<ServiceStatusIndicator isLiveMode={false} />);
    assert.equal(signals[1].aborted, true);
    assert.equal(view.container.textContent, "Monitor simulated");
    await view.render(<ServiceStatusIndicator isLiveMode />);
    await view.close();
    assert.equal(signals[2].aborted, true);
  } finally { globalThis.fetch = originalFetch; AbortSignal.timeout = originalTimeout; if (view.container.isConnected) await view.close(); }
});

test("VM controls persist registrations, scope measurements and launch/stop selected targets", async () => {
  const view = mount();
  const originalFetch = globalThis.fetch;
  const local = { vm_id: "local", name: "Local VM", base_url: "http://127.0.0.1:3000", is_local: true };
  const remote = { vm_id: "remote", name: "Clone", base_url: "http://192.168.56.11:3000", is_local: false };
  let vms = [local, remote];
  let batches: any[] = [];
  let finishLaunch: ((response: Response) => void) | undefined;
  const launches: any[] = [];
  const registrations: any[] = [];
  const removals: string[] = [];
  globalThis.fetch = async (input, options) => {
    const url = String(input);
    const method = options?.method ?? "GET";
    const body = options?.body ? JSON.parse(String(options.body)) : undefined;
    if (url === "/api/8009/vms" && method === "GET") return reply(vms);
    if (url === "/api/8009/vms" && method === "POST") {
      registrations.push(body);
      const vm = { ...body, vm_id: "new", is_local: false };
      vms = [...vms, vm]; return reply(vm, 201);
    }
    if (url === "/api/8009/vms/new" && method === "DELETE") {
      removals.push(url); vms = vms.filter(vm => vm.vm_id !== "new"); return reply({ removed: true });
    }
    if (url === "/api/8009/experiment-batches?limit=20") return reply(batches);
    if (url === "/api/8009/experiment-batches?active_only=true&limit=50") return reply(batches.filter(batch => batch.status === "running"));
    if (url.endsWith("/metrics/latest")) {
      const vm = vms.find(vm => url.includes(`/vms/${vm.vm_id}/`));
      assert.ok(vm);
      return reply({ vm_id: vm.vm_id, vm_name: vm.name,
        cpu: { cpu_usage_percent: vm.is_local ? 32 : 77 }, memory: null, network: null });
    }
    if (url === "/api/8009/experiments/launch" && method === "POST") {
      launches.push(body);
      return new Promise<Response>(resolve => { finishLaunch = resolve; });
    }
    if (url === "/api/8009/experiment-batches/batch-1/stop" && method === "POST") {
      batches = [{ ...batches[0], status: "stopped", members: batches[0].members.map((member: any) => ({ ...member, status: "completed" })) }];
      return reply(batches[0]);
    }
    throw new Error(`Unexpected request: ${method} ${url}`);
  };
  const click = async (element: Element) => act(async () => { element.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
  const fill = async (id: string, value: string) => act(async () => {
    const element = view.container.querySelector<HTMLInputElement | HTMLSelectElement>(`#${id}`)!;
    const prototype = element.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, "value")!.set!.call(element, value);
    element.dispatchEvent(new Event(element.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
  });
  const button = (label: string) => [...view.container.querySelectorAll("button")].find(item => item.textContent === label)!;
  try {
    await view.render(<VMs />);
    assert.match(view.container.textContent!, /32.0%/);
    await fill("metrics-vm", "remote");
    assert.match(view.container.textContent!, /77.0%/);
    assert.doesNotMatch(view.container.textContent!, /32.0%/);
    await fill("vm-name", "Another clone");
    await fill("vm-address", "http://192.168.56.12:3000");
    await click(button("Register VM"));
    assert.deepEqual(registrations, [{ name: "Another clone", base_url: "http://192.168.56.12:3000" }]);
    const newRow = [...view.container.querySelectorAll("button")].find(item => item.textContent === "Remove" && item.parentElement?.textContent?.includes("Another clone"))!;
    await click(newRow);
    assert.equal(removals.length, 1);
    const checkbox = [...view.container.querySelectorAll('input[type="checkbox"]')].find(item => item.parentElement?.textContent === "Clone")!;
    await click(checkbox);
    const launchForm = button("Launch experiment").closest("form")!;
    await act(async () => {
      launchForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      launchForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    assert.equal(launches.length, 1, "rapid submissions must send only one launch");
    assert.deepEqual(launches[0].vm_ids, ["local", "remote"]);
    assert.deepEqual(launches[0].parameters, { cpu_percent: 10, duration_seconds: 15 });
    batches = [{ batch_id: "batch-1", name: "two VMs", status: "running", members: [local, remote].map(vm => ({ vm, vm_id: vm.vm_id, vm_name: vm.name, status: "running" })) }];
    await act(async () => finishLaunch!(reply(batches[0], 201)));
    assert.match(view.container.textContent!, /Clone: running/);
    await click(button("Stop batch"));
    assert.match(view.container.textContent!, /Clone: completed/);
    assert.equal(batches[0].status, "stopped");
  } finally { await view.close(); globalThis.fetch = originalFetch; }
});

test("older active batches remain visible alongside recent history without duplicates", async () => {
  const { fetchVmBatches } = await import("../client/src/lib/vm-api");
  const originalFetch = globalThis.fetch;
  const older = { batch_id: "older-running", status: "running" };
  const recent = Array.from({ length: 20 }, (_, index) => ({ batch_id: `completed-${index}`, status: "completed" }));
  globalThis.fetch = async (url) => reply(String(url).includes("active_only=true") ? [older] : recent);
  try {
    const batches = await fetchVmBatches();
    assert.equal(batches.length, 21);
    assert.equal(batches[0].batch_id, "older-running");
    recent[0] = older;
    assert.equal((await fetchVmBatches()).filter(batch => batch.batch_id === older.batch_id).length, 1);
  } finally { globalThis.fetch = originalFetch; }
});

test("VM selection cancels old metrics, rejects another VM's readings, and limits launch targets", async () => {
  const view = mount();
  const originalFetch = globalThis.fetch;
  const vms = ["local", "remote", ...Array.from({ length: 16 }, (_, i) => `extra-${i}`)]
    .map(id => ({ vm_id: id, name: id, base_url: "http://192.168.56.11:3000", is_local: id === "local" }));
  const pending: AbortSignal[] = [];
  globalThis.fetch = async (input, options) => {
    const url = String(input);
    if (url === "/api/8009/vms") return reply(vms);
    if (url.includes("/experiment-batches?")) return reply([]);
    if (url.includes("/vms/remote/metrics")) return reply({ vm_id: "another-vm", cpu: { cpu_usage_percent: 99 } });
    if (url.includes("/vms/local/metrics")) return new Promise<Response>((_resolve, reject) => {
      const signal = options!.signal!;
      pending.push(signal);
      signal.addEventListener("abort", () => reject(signal.reason), { once: true });
    });
    throw new Error(`Unexpected request: ${url}`);
  };
  try {
    await view.render(<VMs />);
    await act(async () => {
      const select = view.container.querySelector<HTMLSelectElement>("#metrics-vm")!;
      select.value = "remote";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    assert.equal(pending[0].aborted, true);
    assert.match(view.container.textContent!, /different VM/);
    assert.doesNotMatch(view.container.textContent!, /99.0%/);
    const targets = [...view.container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')];
    for (const checkbox of targets.slice(1)) await act(async () => checkbox.click());
    assert.equal(targets.filter(item => item.checked).length, 16);
    assert.equal(targets.filter(item => item.disabled).length, 2);
    await act(async () => targets[1].click());
    assert.equal(targets.filter(item => item.disabled).length, 0);
  } finally { await view.close(); globalThis.fetch = originalFetch; }
});

test("VM requests use deadlines and preserve useful gateway error messages", async () => {
  const { fetchVMs, registerVM, fetchVmMetrics } = await import("../client/src/lib/vm-api");
  const originalFetch = globalThis.fetch;
  const originalTimeout = AbortSignal.timeout;
  const deadlines: number[] = [];
  AbortSignal.timeout = milliseconds => { deadlines.push(milliseconds); return new AbortController().signal; };
  globalThis.fetch = async () => reply({ error: "VM API 8009 is unavailable" }, 502);
  try {
    await assert.rejects(fetchVMs(), /VM API 8009 is unavailable/);
    globalThis.fetch = async () => new Response("backend unavailable", { status: 503 });
    await assert.rejects(fetchVMs(), /HTTP 503/);
    await assert.rejects(registerVM("Clone", "http://192.168.56.11:3000"), /HTTP 503/);
    globalThis.fetch = async () => new Response("<html>wrong response</html>");
    await assert.rejects(fetchVmMetrics("local"), /invalid response/);
    assert.deepEqual(deadlines, [30000, 30000, 120000, 30000]);
  } finally { globalThis.fetch = originalFetch; AbortSignal.timeout = originalTimeout; }
});
