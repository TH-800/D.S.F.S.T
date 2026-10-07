import type { Express, Request, Response, NextFunction } from "express";
import { request as httpRequest } from "node:http";

// One browser origin per VM; the Python services stay on guest loopback.
export function registerApiProxy(app: Express, vmIp = process.env.DSFST_VM_IP) {
  const webPort = process.env.PORT || "3000";
  const hosts = ["localhost", "127.0.0.1", ...(vmIp ? [vmIp] : [])];
  app.use((req: Request, res: Response, next: NextFunction) => {
    const host = req.headers.host || "";
    if (!hosts.some(value => host === `${value}:${webPort}` || (webPort === "80" && host === value))) {
      res.status(400).json({ error: "Unknown VM host" });
      return;
    }
    const origin = req.headers.origin;
    if (origin && origin !== `http://${host}`) {
      res.status(403).json({ error: "Use this VM's own browser address" });
      return;
    }
    next();
  });

  app.get(["/api", "/api/"], (_req, res) => {
    res.json({
      services: Array.from({ length: 11 }, (_, index) => ({
        port: 8000 + index,
        docs: `/api/${8000 + index}/docs`,
      })),
      metrics: "/api/8008/metrics/latest",
      experiments: "/api/8008/experiments",
      state: "/api/8009/state",
    });
  });

  // Register before express.json so the body streams to FastAPI unchanged.
  app.use("/api", (req, res) => {
    const match = req.url.match(/^\/(800[0-9]|8010)(\/[^#]*)?$/);
    if (!match) {
      res.status(404).json({ error: "API service must be 8000 through 8010" });
      return;
    }
    if (!["GET", "HEAD", "POST", "DELETE", "OPTIONS"].includes(req.method)) {
      res.status(405).json({ error: "Unsupported API method" });
      return;
    }
    const port = Number(match[1]);
    const path = match[2] || "/";
    const headers = { ...req.headers };
    for (const name of ["connection", "transfer-encoding", "upgrade", "forwarded", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto"]) {
      delete headers[name];
    }
    headers.host = `127.0.0.1:${port}`;
    if (headers.origin) headers.origin = "http://127.0.0.1:3000";
    const upstream = httpRequest({ hostname: "127.0.0.1", port, path, method: req.method, headers }, reply => {
      res.status(reply.statusCode || 502);
      for (const [name, value] of Object.entries(reply.headers)) {
        if (value !== undefined && !["connection", "transfer-encoding"].includes(name)) {
          // A local redirect should retain the browser's API prefix.
          if (name === "location" && typeof value === "string") {
            const local = `http://127.0.0.1:${port}`;
            res.setHeader(name, value.startsWith(local) ? value.replace(local, "") : value);
          } else res.setHeader(name, value);
        }
      }
      reply.on("error", () => res.destroy());
      reply.pipe(res);
    });
    upstream.setTimeout(120_000, () => upstream.destroy(new Error("API timeout")));
    upstream.on("error", () => {
      if (!res.headersSent) res.status(502).json({ error: `VM API ${port} is unavailable` });
      else res.destroy();
    });
    req.on("aborted", () => upstream.destroy());
    res.on("close", () => { if (!res.writableEnded) upstream.destroy(); });
    req.pipe(upstream);
  });
}
