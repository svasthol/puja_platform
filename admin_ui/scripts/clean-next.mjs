import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const adminRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const nextDir = path.join(adminRoot, ".next");
try {
  fs.rmSync(nextDir, { recursive: true, force: true });
  console.log("[clean-next] removed .next");
} catch (err) {
  console.warn("[clean-next] skip:", err.message);
}