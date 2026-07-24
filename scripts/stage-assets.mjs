import { createHash } from "node:crypto";
import { cp, mkdir, readFile, readdir, rm, stat } from "node:fs/promises";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "data", "tiles-002");
const staticSource = join(root, "static");
const output = join(root, "public");
const checkOnly = process.argv.includes("--check");

// OSMAND-003 se construye por separado para que el staging nunca publique un
// paquete obsoleto respecto a su configuración versionada.
const osfPath = join(staticSource, "previfoc.osf");
invariant((await stat(osfPath)).isFile(), "missing OSMAND-003 package; run pnpm build:osf");

const expected = {
  geometryVersion:
    "sha256:e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0",
  manifest:
    "bf441e744a7b82d63b455ca4ec66a92afb8e2611d4d4d918dc88b3c738c98cd2",
  inventory:
    "464e34c9db51811977898fea42d5b17c2ba0e5b25d09feb292aac60790121480",
  transparent:
    "679644f8ef3768bbe373bc2db7d50c3d9f133013cb927154fc920a4471616809",
  coveredTiles: 9507,
  maxAssets: 19000,
};

async function sha256(path) {
  return createHash("sha256").update(await readFile(path)).digest("hex");
}

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

function invariant(condition, message) {
  if (!condition) throw new Error(message);
}

const manifestPath = join(source, "manifest.json");
const inventoryPath = join(source, "tiles.sha256");
const transparentPath = join(source, "transparent.png");

invariant(
  (await sha256(manifestPath)) === expected.manifest,
  "TILES-002 manifest hash does not match the frozen contract",
);
invariant(
  (await sha256(inventoryPath)) === expected.inventory,
  "TILES-002 inventory hash does not match the frozen contract",
);
invariant(
  (await sha256(transparentPath)) === expected.transparent,
  "TILES-002 transparent tile hash does not match the frozen contract",
);

const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
invariant(manifest.geometry_version === expected.geometryVersion, "geometry_version changed");
invariant(manifest.format_version === "previfoc-indexed-template-v2", "tile format version changed");
invariant(manifest.pyramid.tile_assets === expected.coveredTiles, "covered tile count changed");

const inventoryLines = (await readFile(inventoryPath, "utf8"))
  .trim()
  .split("\n");
invariant(inventoryLines.length === expected.coveredTiles, "inventory line count changed");

const entries = inventoryLines.map((line) => {
  const match = /^([0-9a-f]{64})  ((?:6|7|8|9|10|11|12|13|14)\/\d+\/\d+\.png)$/.exec(line);
  invariant(match, `invalid inventory entry: ${line}`);
  return { hash: match[1], relativePath: match[2] };
});

const publicStaticPaths = ["index.html", "styles.css", "app.js", "previfoc.osf"];
const staticFiles = publicStaticPaths.map((relativePath) =>
  join(staticSource, relativePath),
);
for (const staticFile of staticFiles) {
  invariant((await stat(staticFile)).isFile(), `missing public static asset: ${relative(staticSource, staticFile)}`);
}
const assetCount = entries.length + 1 + staticFiles.length; // transparent.png plus web assets.
invariant(assetCount < expected.maxAssets, `asset limit exceeded: ${assetCount}`);

if (!checkOnly) {
  await rm(output, { recursive: true, force: true });
  await mkdir(join(output, "tiles"), { recursive: true });
  for (const staticFile of staticFiles) {
    const destination = join(output, relative(staticSource, staticFile));
    await mkdir(dirname(destination), { recursive: true });
    await cp(staticFile, destination);
  }
  await cp(transparentPath, join(output, "tiles", "transparent.png"));
}

let tileBytes = 0;
for (const entry of entries) {
  const inputPath = join(source, entry.relativePath);
  const inputStat = await stat(inputPath);
  tileBytes += inputStat.size;
  invariant((await sha256(inputPath)) === entry.hash, `tile hash changed: ${entry.relativePath}`);

  const stagedPath = join(output, "tiles", entry.relativePath);
  if (!checkOnly) {
    await mkdir(dirname(stagedPath), { recursive: true });
    await cp(inputPath, stagedPath);
  } else {
    invariant((await sha256(stagedPath)) === entry.hash, `staged tile differs: ${entry.relativePath}`);
  }
}

invariant(tileBytes === manifest.pyramid.tile_bytes, "tile byte count changed");
if (checkOnly) {
  invariant((await sha256(join(output, "tiles", "transparent.png"))) === expected.transparent, "staged transparent tile differs");
}
for (const staticFile of staticFiles) {
  const relativePath = relative(staticSource, staticFile);
  invariant(
    (await sha256(join(output, relativePath))) === (await sha256(staticFile)),
    `staged static asset differs: ${relativePath}`,
  );
}
invariant((await listFiles(output)).length === assetCount, "staged asset count differs");

console.log(
  JSON.stringify({
    mode: checkOnly ? "check" : "stage",
    assets: assetCount,
    covered_tiles: entries.length,
    tile_bytes: tileBytes,
    limit: expected.maxAssets,
    source: "data/tiles-002 (read-only)",
    output: "public",
  }),
);
