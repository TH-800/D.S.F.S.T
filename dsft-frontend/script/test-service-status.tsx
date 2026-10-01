// Render-only checks for SCRUM-12. No VM, network or experiment is started.
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ServiceStatusIndicator from "../client/src/components/ServiceStatusIndicator";

for (const [online, state, text, color] of [
  [true, "online", "Online", "bg-emerald-500"],
  [false, "offline", "Unreachable", "bg-red-500"],
  [null, "unknown", "Not checked", "bg-slate-400"],
] as const) {
  const html = renderToStaticMarkup(
    <ServiceStatusIndicator label="CPU API" online={online} />,
  );
  assert.ok(html.includes(`data-state="${state}"`));
  assert.ok(html.includes(text));
  assert.ok(html.includes(color));
  assert.ok(html.includes('role="status"'));
  assert.ok(html.includes(`aria-label="CPU API: ${text}"`));
}

const mock = renderToStaticMarkup(<ServiceStatusIndicator online={true} mock />);
assert.ok(mock.includes("simulated"));
console.log("PASS: online, offline, unknown, accessible labels and simulated status.");
