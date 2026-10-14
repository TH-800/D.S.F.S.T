// SCRUM-18/20/21 interaction regressions. All requests are simulated; no VM faults.
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import React from "react";
const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost:3000', pretendToBeVisual: true });
for (const key of ['window','document','HTMLElement','DocumentFragment','Element','Node','NodeFilter','HTMLInputElement','MutationObserver','CustomEvent','Event','localStorage','getComputedStyle']) {
  Object.defineProperty(globalThis, key, { value: (dom.window as any)[key], configurable: true, writable: true });
}
Object.assign(globalThis, { React, requestAnimationFrame: dom.window.requestAnimationFrame.bind(dom.window), cancelAnimationFrame: dom.window.cancelAnimationFrame.bind(dom.window) });
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
const { render, screen, fireEvent, waitFor, cleanup } = await import('@testing-library/react');
const { default: Guide, GUIDE_KEY } = await import('../client/src/components/FirstUseGuide');
const { default: VMs } = await import('../client/src/pages/VMs');
const { useToast } = await import('../client/src/hooks/use-toast');
const { startExperiment, stopExperiment } = await import('../client/src/lib/api');
function ToastProbe() {
  const { toasts } = useToast();
  return <div data-testid="toasts">{toasts.map(t => <div key={t.id}>{t.title} {t.description}</div>)}</div>;
}
const { default: Experiments } = await import('../client/src/pages/Experiments');
const { AppProvider, useAppState } = await import('../client/src/lib/store');
function ModeSwitch() {
  const { setIsLiveMode } = useAppState();
  return <button onClick={() => setIsLiveMode(true)}>Use live for test</button>;
}
let calls: {url: string; method: string; body: any}[] = [];
let vms = [
  { vm_id: 'local', name: 'Ubuntu local', base_url: 'http://127.0.0.1:3000', is_local: true },
  { vm_id: 'remote', name: 'Ubuntu clone', base_url: 'http://192.168.56.11:3000', is_local: false },
];
let batches: any[] = [];
let launchStatus = 'running';
let stopStatus = 'stopped';
let registryFails = false;
let pendingLaunch: (() => void) | undefined;
let delayLaunch = false;
let singleStatus = 'running';
globalThis.fetch = async (input: any, init: any = {}) => {
  const url = String(input); const method = init.method || 'GET';
  const body = init.body ? JSON.parse(init.body) : undefined;
  calls.push({url, method, body});
  if (url === '/api/8009/state') return Response.json({state: 'idle', active_experiment_id: null});
  if (url.startsWith('/api/8008/experiments') || url.startsWith('/api/8008/presets')) return Response.json([]);
  if (url === '/api/8009/experiments' && method === 'POST') return Response.json({experiment_id: 'test', status: 'created'});
  if (url.endsWith('/vms')) return registryFails ? Response.json({detail: 'Registry unavailable'}, {status: 503}) : Response.json(vms);
  if (url.includes('/metrics/latest')) return Response.json({});
  if (url.includes('/experiment-batches?')) return Response.json(batches);
  if (url.endsWith('/experiments/launch')) {
    if (delayLaunch) await new Promise<void>(resolve => { pendingLaunch = resolve; });
    const batch = { batch_id: 'batch-1', name: body.name, status: launchStatus, members: body.vm_ids.map((id: string) => ({ vm_id: id, vm_name: id, vm: vms.find(v => v.vm_id === id), status: launchStatus, experiment_id: null, error: launchStatus === 'running' ? null : 'Reset unconfirmed' })) };
    batches = [batch];
    return Response.json(batch, { status: launchStatus === 'running' ? 201 : 207 });
  }
  if (url.includes('/experiment-batches/') && url.endsWith('/stop')) {
    batches = batches.map(b => ({...b, status: stopStatus}));
    return Response.json(batches[0], {status: stopStatus === 'partial_failure' ? 207 : 200});
  }
  if (url.endsWith('/experiments/test/start') || url.endsWith('/experiments/test/stop')) return Response.json({ status: singleStatus });
  throw new Error('Unexpected request: ' + url);
};

// Guide persists dismiss/finish, can be reopened, and performs no network operations.
render(<Guide />);
assert.ok(screen.getByRole('dialog'));
assert.ok(screen.getByRole('button', { name: 'Back' }).hasAttribute('disabled'));
fireEvent.click(screen.getByRole('button', {name: 'Next'}));
assert.ok(screen.getByText('Dashboard and connection lights'));
fireEvent.click(screen.getByRole('button', {name: 'Back'}));
fireEvent.click(screen.getByRole('button', {name: 'Skip guide'}));
assert.equal(localStorage.getItem(GUIDE_KEY), 'true');
cleanup(); render(<Guide />);
assert.equal(screen.queryByRole('dialog'), null);
fireEvent.click(screen.getByRole('button', {name: 'Quick guide'}));
for(let i=0;i<4;i++) fireEvent.click(screen.getByRole('button', {name: 'Next'}));
fireEvent.click(screen.getByRole('button', {name: 'Finish guide'}));
assert.equal(screen.queryByRole('dialog'), null);
assert.equal(calls.length, 0);
cleanup();
const storagePrototype = Object.getPrototypeOf(localStorage);
const getItem = storagePrototype.getItem, setItem = storagePrototype.setItem;
storagePrototype.getItem = () => { throw new Error('Storage blocked'); };
storagePrototype.setItem = () => { throw new Error('Storage blocked'); };
render(<Guide />);fireEvent.click(screen.getByRole('button', {name: 'Skip guide'}));cleanup();
storagePrototype.getItem = getItem;storagePrototype.setItem = setItem;

render(<><VMs /><ToastProbe /></>);
await screen.findByRole('checkbox', {name: 'Ubuntu clone'});
assert.ok(screen.getByRole('button', {name: 'Launch on 0 VM(s)'}).hasAttribute('disabled'));
fireEvent.click(screen.getByRole('checkbox', {name: 'Ubuntu local'}));
fireEvent.click(screen.getByRole('checkbox', {name: 'Ubuntu clone'}));
fireEvent.change(screen.getByLabelText('CPU percent'), {target: {value: '25'}});
fireEvent.change(screen.getByLabelText('Duration seconds'), {target: {value: '10'}});
delayLaunch = true;
fireEvent.click(screen.getByRole('button', {name: 'Launch on 2 VM(s)'}));
await waitFor(() => assert.ok(pendingLaunch));
assert.ok(!screen.getByTestId('toasts').textContent?.includes('Experiment started'));
fireEvent.submit(screen.getByRole('button', {name: 'Working...'}).closest('form')!);
assert.equal(calls.filter(c => c.url.endsWith('/experiments/launch')).length, 1);
pendingLaunch!();delayLaunch = false;
await waitFor(() => assert.match(screen.getByTestId('toasts').textContent!, /Experiment started on 2/));
const sent = calls.find(c => c.url.endsWith('/experiments/launch'))!.body;
assert.deepEqual(sent.vm_ids, ['local','remote']);
assert.deepEqual(sent.parameters, {cpu_percent: 25, duration_seconds: 10});
stopStatus = 'partial_failure';
fireEvent.click(screen.getByRole('button', {name: 'Stop batch'}));
await waitFor(() => assert.match(screen.getByTestId('toasts').textContent!, /not confirmed/));
assert.ok(!screen.getByTestId('toasts').textContent?.includes('Batch stopped'));
await waitFor(() => assert.ok(!screen.getByRole('button', {name: 'Stop batch'}).hasAttribute('disabled')));
stopStatus = 'stopped';fireEvent.click(screen.getByRole('button', {name: 'Stop batch'}));
await waitFor(() => assert.match(screen.getByTestId('toasts').textContent!, /Batch stopped/));
await waitFor(() => assert.ok(!screen.getByRole('button', {name: 'Launch on 2 VM(s)'}).hasAttribute('disabled')));
launchStatus = 'partial_failure';
fireEvent.click(screen.getByRole('button', {name: 'Launch on 2 VM(s)'}));
await waitFor(() => assert.match(screen.getByTestId('toasts').textContent!, /not confirmed/));
assert.ok(!screen.getByTestId('toasts').textContent?.includes('Experiment started'));
cleanup();
// Selection cap and empty/disconnected registry never permit a launch.
vms = Array.from({length: 17}, (_,i) => ({vm_id: 'vm'+i, name:'VM '+i, base_url:'http://192.168.56.11:3000',is_local:false}));
render(<VMs />);await screen.findByRole('checkbox', {name:'VM 16'});
fireEvent.click(screen.getByRole('button', {name: 'Select first 16'}));
assert.equal(screen.getAllByRole('checkbox').filter(x => (x as HTMLInputElement).checked).length,16);
assert.ok(screen.getByRole('checkbox', {name:'VM 16'}).hasAttribute('disabled'));
fireEvent.click(screen.getByRole('button', {name:'Clear selection'}));
assert.ok(screen.getByRole('button', {name:'Launch on 0 VM(s)'}).hasAttribute('disabled'));
cleanup();registryFails = true;render(<VMs />);
await screen.findByText('Registry unavailable');
assert.ok(screen.getByRole('button', {name:'Launch on 0 VM(s)'}).hasAttribute('disabled'));cleanup();
// HTTP 200 alone is not confirmation of a single-VM operation.
singleStatus = 'partial_failure';
await assert.rejects(startExperiment('test'), /did not confirm/);
await assert.rejects(stopExperiment('test'), /did not confirm/);
singleStatus = 'running';await startExperiment('test');
singleStatus = 'completed';await stopExperiment('test');
// Single-VM notifications distinguish simulations and require semantic confirmation.
render(<AppProvider><Experiments /><ModeSwitch /><ToastProbe /></AppProvider>);
const beforeMock = calls.length;
fireEvent.click(screen.getByTestId('button-start-experiment'));
await waitFor(() => assert.match(screen.getByTestId('toasts').textContent!, /Mock experiment started/));
assert.equal(calls.length, beforeMock);
fireEvent.click(screen.getByRole('button', {name: 'Stop'}));
await waitFor(() => assert.match(screen.getByTestId('toasts').textContent!, /Mock experiment stopped/));
cleanup();
render(<AppProvider><Experiments /><ModeSwitch /><ToastProbe /></AppProvider>);
fireEvent.click(screen.getByText('Use live for test'));
singleStatus = 'partial_failure';
fireEvent.click(screen.getByTestId('button-start-experiment'));
await waitFor(() => assert.match(screen.getByTestId('toasts').textContent!, /Experiment failed to start/));
assert.equal(screen.queryByRole('button', {name:'Stop'}), null);
singleStatus = 'running';fireEvent.click(screen.getByTestId('button-start-experiment'));
await waitFor(() => assert.match(screen.getByTestId('toasts').textContent!, /Experiment started/));
singleStatus = 'partial_failure';fireEvent.click(screen.getByRole('button', {name:'Stop'}));
await waitFor(() => assert.match(screen.getByTestId('toasts').textContent!, /Reset failed/));
await screen.findByRole('button', {name:'Stop'});
singleStatus = 'completed';fireEvent.click(screen.getByRole('button', {name:'Stop'}));
await waitFor(() => assert.match(screen.getByTestId('toasts').textContent!, /Experiment stopped/));
cleanup();
console.log('PASS: first-use persistence/reopen/storage failure; two-VM payload and pending guard; partial launch/reset; confirmed toasts; 16-target cap; registry failure; semantic single-VM confirmations. No real injections.');
process.exit(0);
