import assert from "node:assert/strict";
import { createServer, request, type Server } from "node:http";
import { once } from "node:events";
import { test } from "node:test";
import express from "express";
import { registerApiProxy } from "./api-proxy";

const close = (server: Server) => new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
const call = (url: string, options: { method?: string; headers?: Record<string, string>; body?: string } = {}) =>
  new Promise<{ status: number; json: () => any }>((resolve, reject) => {
    const req = request(url, { method: options.method, headers: options.headers }, async res => {
      let body = "";
      for await (const chunk of res) body += chunk;
      resolve({ status: res.statusCode!, json: () => JSON.parse(body) });
    });
    req.on("error", reject);
    req.end(options.body);
  });
test("VM gateway forwards JSON, queries and status codes and rejects other hosts/services", async () => {
  const upstream = createServer(async (req, res) => {
    let body = "";
    for await (const chunk of req) body += chunk;
    res.writeHead(req.url === "/bad" ? 422 : 200, { "content-type": "application/json" });
    res.end(JSON.stringify({ path: req.url, method: req.method, body, host: req.headers.host, origin: req.headers.origin }));
  });
  const gateway = createServer();
  let oldPort = process.env.PORT;
  try {
    upstream.listen(8008, "127.0.0.1"); await once(upstream, "listening");
    gateway.listen(0, "127.0.0.1"); await once(gateway, "listening");
    const port = (gateway.address() as { port: number }).port;
    process.env.PORT = String(port);
    const app = express();
    registerApiProxy(app, "192.168.56.10");
    gateway.on("request", app);
    const base = `http://127.0.0.1:${port}`;
    const headers = { host: `192.168.56.10:${port}`, origin: `http://192.168.56.10:${port}` };
    const reply = await call(`${base}/api/8008/experiments?limit=2`, { method: "POST", headers: { ...headers, "content-type": "application/json" }, body: '{"name":"Windows"}' });
    assert.equal(reply.status, 200);
    assert.deepEqual(await reply.json(), { path: "/experiments?limit=2", method: "POST", body: '{"name":"Windows"}', host: "127.0.0.1:8008", origin: "http://127.0.0.1:3000" });
    assert.equal((await fetch(`${base}/api/8008/bad`)).status, 422);
    assert.equal((await fetch(`${base}/api/8086/health`)).status, 404);
    assert.equal((await fetch(`${base}/api/8008/health`, { headers: { origin: "https://example.com" } })).status, 403);
    assert.equal((await call(`${base}/api/8008/health`, { headers: { host: `example.com:${port}` } })).status, 400);
    const directory = await (await fetch(`${base}/api`)).json() as { services: unknown[] };
    assert.equal(directory.services.length, 11);
    await close(upstream);
    assert.equal((await fetch(`${base}/api/8008/health`)).status, 502);
  } finally {
    if (oldPort === undefined) delete process.env.PORT; else process.env.PORT = oldPort;
    if (upstream.listening) await close(upstream);
    if (gateway.listening) await close(gateway);
  }
});
