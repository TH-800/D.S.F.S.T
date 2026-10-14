# SCRUM-18, SCRUM-20 and SCRUM-21

Prepared for Momin Khawaja's PPP work, October 14, 2026. AI-assisted implementation.

## Scope

- SCRUM-18 extends Tarun's existing VMs page and batch API. Users explicitly check targets (none selected initially), see a selection count and target names, select all up to the backend's 16-target maximum, clear selection, and launch one configuration on those VMs. Empty/stale/failed-registry selections cannot launch. Pending operations reject duplicate submissions. Partial launches and unconfirmed resets remain errors with per-VM results. The VMs page is explicitly live, independently of the dashboard's Mock setting.
- SCRUM-20 adds a five-step accessible dialog on first use. It describes Dashboard, VMs, experiments/presets, logs/reports and recovery limitations. Next, Back, Skip, Close and Finish are supported. Dismissal persists in browser localStorage; blocked storage does not crash the app. Quick guide in the header reopens it. The guide does not navigate, change modes or launch requests.
- SCRUM-21 builds on existing single-VM toasts. Real start/stop success requires the expected backend status, not merely HTTP 200. Mock toasts say they are simulated. Batch launch/stop actions now show confirmation or error toasts. Repeated single-VM start/stop clicks are guarded while pending.

## Integration base

This branch descends from fa8e890, the v2 bundle previously installed in Momin's Ubuntu worktree. It includes main-based-dev-branch da10f3f and the earlier SCRUM-12/16 integration and local-backend-preservation changes. The remote momin-scrum-12-16-integration branch has an alternative implementation, so do not blindly merge both preset implementations. No shared branch is overwritten.

## Checks

From dsft-frontend:

```bash
npm ci
npm run check
npm run test:frontend
npm run test:ppp
npm run build
```

The gateway test in test:frontend binds port 8008; stop the local application before running that suite, or use an isolated checkout/machine. test:ppp uses a simulated DOM and API responses and does not run real injections. It covers guide persistence/reopen/blocked storage, selected VM payloads, pending submissions, selection limits, disconnected registry, partial batch launch/reset and single-VM success/failure notifications.

## Live acceptance before marking Done

1. Open the rebuilt frontend with fresh browser storage. Navigate and dismiss the guide, reload, and reopen it using Quick guide.
2. Verify single-VM Mock start/stop messages are labelled simulated. On a prepared idle test VM, verify live start/stop confirmations reflect backend results.
3. On VMs, register two reachable prepared VM API addresses. Check the target names and use a short CPU test within the configured limits. Confirm both per-VM results and the batch stop outcome. No two-real-VM experiment was executed in the coding environment.
4. Test an unavailable target: it must produce an error without an all-success toast. Investigate unknown reset states before retrying.

A code push is not a deployment: Momin's Windows and Ubuntu checkouts need to be updated and the frontend rebuilt/restarted separately. Existing npm dependency audit findings from the prior setup are outside these three tickets.
