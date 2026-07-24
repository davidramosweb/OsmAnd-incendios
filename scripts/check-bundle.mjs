import { readdir, stat } from "node:fs/promises";
import { extname, join, resolve } from "node:path";

const directory = resolve(process.argv[2] ?? "dist/worker-dry-run");
const maxBundleBytes = 1024 * 1024;

async function listFiles(path) {
  const entries = await readdir(path, { withFileTypes: true });
  const nested = await Promise.all(
    entries.map((entry) => {
      const child = join(path, entry.name);
      return entry.isDirectory() ? listFiles(child) : [child];
    }),
  );
  return nested.flat();
}

const files = await listFiles(directory);
const bundleFiles = files.filter((path) => [".js", ".mjs"].includes(extname(path)));
if (bundleFiles.length === 0) throw new Error(`no Worker bundle found in ${directory}`);

let bundleBytes = 0;
for (const path of bundleFiles) bundleBytes += (await stat(path)).size;
if (bundleBytes > maxBundleBytes) {
  throw new Error(`Worker bundle ${bundleBytes} bytes exceeds guard ${maxBundleBytes} bytes`);
}

console.log(
  JSON.stringify({
    bundle_bytes: bundleBytes,
    guard_bytes: maxBundleBytes,
    bundle_files: bundleFiles.length,
  }),
);
