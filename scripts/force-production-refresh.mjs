import { readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";

const DEFAULT_URL =
  "https://previfoc.davidramosweb.com/internal/deploy-refresh";
const KEYCHAIN_ACCOUNT = "previfoc-deployer";
const KEYCHAIN_SERVICE = "previfoc-deploy-hook";

function unquote(value) {
  const trimmed = value.trim();
  if (
    trimmed.length >= 2 &&
    ((trimmed.startsWith('"') && trimmed.endsWith('"')) ||
      (trimmed.startsWith("'") && trimmed.endsWith("'")))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

async function tokenFromDevVars() {
  try {
    const contents = await readFile(new URL("../.dev.vars", import.meta.url), "utf8");
    for (const line of contents.split(/\r?\n/u)) {
      const match = /^\s*DEPLOY_HOOK_TOKEN\s*=\s*(.+?)\s*$/u.exec(line);
      if (match) return unquote(match[1]);
    }
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  return undefined;
}

function tokenFromMacOsKeychain() {
  if (process.platform !== "darwin") return undefined;
  const result = spawnSync(
    "security",
    [
      "find-generic-password",
      "-w",
      "-a",
      KEYCHAIN_ACCOUNT,
      "-s",
      KEYCHAIN_SERVICE,
    ],
    { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] },
  );
  return result.status === 0 ? result.stdout.trim() : undefined;
}

const token =
  process.env.DEPLOY_HOOK_TOKEN ??
  tokenFromMacOsKeychain() ??
  (await tokenFromDevVars());

if (!token) {
  throw new Error(
    "DEPLOY_HOOK_TOKEN is missing (environment, macOS Keychain, or .dev.vars)",
  );
}

const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 90_000);
let response;
try {
  response = await fetch(process.env.PREVIFOC_REFRESH_URL ?? DEFAULT_URL, {
    method: "POST",
    headers: {
      authorization: `Bearer ${token}`,
      accept: "application/json",
    },
    signal: controller.signal,
  });
} finally {
  clearTimeout(timeout);
}

const body = await response.text();
if (!response.ok) {
  throw new Error(`production refresh failed with HTTP ${response.status}: ${body}`);
}

const result = JSON.parse(body);
if (result.ok !== true) {
  throw new Error(`production refresh did not complete: ${body}`);
}
console.log(`Production state refresh: ${result.outcome}`);
