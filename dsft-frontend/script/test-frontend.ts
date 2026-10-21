import { build } from "esbuild";
import { mkdir } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const directory = "node_modules/.cache/dsfst-tests";
await mkdir(directory, { recursive: true });
const outfile = `${directory}/frontend.test.mjs`;
await build({
  entryPoints: ["script/frontend.test.tsx", "script/test-environment.ts"],
  outdir: directory,
  outExtension: { ".js": ".mjs" },
  bundle: true,
  platform: "node",
  format: "esm",
  packages: "external",
  jsx: "automatic",
});
const environment = pathToFileURL(resolve(directory, "test-environment.mjs")).href;
const result = spawnSync(process.execPath, ["--import", environment, resolve(outfile)], { stdio: "inherit" });
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
