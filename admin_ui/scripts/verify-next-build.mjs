/**
 * Pre-flight: detect stale Next.js .next output (missing server chunks → Cannot find module './NNN.js').
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const adminRoot = path.resolve(__dirname, "..");
const logPath = process.env.CURSOR_DEBUG_LOG;
const sessionId = process.env.CURSOR_DEBUG_SESSION ?? "";

function debugLog(payload) {
  if (!logPath) return;
  const line = JSON.stringify({
    sessionId: sessionId || undefined,
    timestamp: Date.now(),
    ...payload,
  });
  fs.appendFileSync(logPath, `${line}\n`, "utf8");
}

const nextDir = path.join(adminRoot, ".next");
const chunksDir = path.join(nextDir, "server", "chunks");
const serverDir = path.join(nextDir, "server");

const chunkRefRe = /require\("\.\/(\d+)\.js"\)/g;

function collectRefs(dir) {
  const refs = new Set();
  if (!fs.existsSync(dir)) return refs;
  const stack = [dir];
  while (stack.length) {
    const cur = stack.pop();
    for (const ent of fs.readdirSync(cur, { withFileTypes: true })) {
      const fp = path.join(cur, ent.name);
      if (ent.isDirectory()) stack.push(fp);
      else if (ent.name.endsWith(".js")) {
        const src = fs.readFileSync(fp, "utf8");
        let m;
        while ((m = chunkRefRe.exec(src)) !== null) refs.add(m[1]);
      }
    }
  }
  return refs;
}

const refs = collectRefs(serverDir);
const missing = [];
const present = [];
for (const id of refs) {
  const fp = path.join(chunksDir, `${id}.js`);
  if (fs.existsSync(fp)) present.push(id);
  else missing.push(id);
}

const buildIdPath = path.join(nextDir, "BUILD_ID");
const hasBuildId = fs.existsSync(buildIdPath);
const data = {
  nextDirExists: fs.existsSync(nextDir),
  hasBuildId,
  chunkRefCount: refs.size,
  chunksPresent: present.length,
  chunksMissing: missing,
  hypothesisId: missing.length ? "H1-stale-next" : "H1-ok",
};

if (hasBuildId && process.env.npm_lifecycle_event === "dev") {
  // eslint-disable-next-line no-console
  console.warn(
    "[verify-next-build] Production .next detected while starting dev. " +
      "If you see Cannot find module './NNN.js', run: npm run dev:clean",
  );
  data.hypothesisId = "H2-build-then-dev";
  data.warnProductionNextWithDev = true;
}

// eslint-disable-next-line no-console
console.log(
  missing.length
    ? `[verify-next-build] STALE: missing server chunks: ${missing.join(", ")} — run: npm run dev:clean`
    : `[verify-next-build] OK (${refs.size} chunk refs)`,
);

debugLog({
  location: "verify-next-build.mjs",
  message: "next chunk verification",
  data,
  runId: process.env.CURSOR_DEBUG_RUN ?? "predev",
});

if (missing.length && process.env.CURSOR_DEBUG_STRICT === "1") {
  process.exit(1);
}