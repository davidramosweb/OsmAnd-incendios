# WORKER-001 — Crear el proyecto Cloudflare del MVP

**Estado:** completado  
**Dependencias:** [OSMAND-002](./OSMAND-002-validacion-dispositivos.md)  
**Siguiente:** [WORKER-002](./WORKER-002-ingesta-previfoc.md)

## Objetivo

Crear el esqueleto desplegable de un único Cloudflare Worker con TypeScript, Static Assets, KV, Cron y pruebas locales, sin implementar todavía la lógica PREVIFOC.

## Contexto

Las plantillas aprobadas en OSMAND-002 son assets inmutables. El Worker sustituye el diseño anterior basado en Fastify, Render y R2.

## Decisiones técnicas

- Gestor: `pnpm`.
- Runtime: Cloudflare Workers ES Modules.
- Configuración: `wrangler.jsonc`.
- Assets: binding `ASSETS` y directorio de publicación local.
- Estado: KV con binding `PREVIFOC_STATE`.
- Cron: `7 * * * *` en UTC.
- Tests: Vitest con integración oficial de Workers.
- Sin framework HTTP, Node server, R2, D1 o Cloudflare Images.

## Alcance

- Inicializar TypeScript, Wrangler, scripts de desarrollo, tests, typecheck y despliegue.
- Definir bindings de producción y preview sin incluir IDs sensibles en fixtures.
- Configurar ejecución del Worker para `/tiles/*`, `/status.json` y `/health`; el resto se sirve como asset.
- Crear handlers mínimos `fetch()` y `scheduled()` con respuestas provisionales.
- Incorporar las plantillas aprobadas al proceso de build/deploy sin regenerarlas.
- Añadir límites y guardas sobre conteo de assets y tamaño del bundle.

## Fuera de alcance

- Descargar PREVIFOC.
- Escribir en KV.
- Recolorear PNG.
- Página final.

## Entregables

- Proyecto instalable con `pnpm install`.
- Configuración Wrangler documentada.
- Worker ejecutable localmente.
- Test mínimo dentro de `workerd`.
- Dry run de despliegue con tamaño y conteo registrados.

## Criterios de aceptación

- [x] `pnpm typecheck` y `pnpm test` terminan correctamente.
- [x] `wrangler dev` sirve un asset estático y ejecuta `/health` desde el Worker.
- [x] El handler programado puede invocarse localmente sin efectos reales.
- [x] Los bindings están tipados.
- [x] El total de assets es inferior a 19.000.
- [x] No existen dependencias de servidor tradicional ni binarios GIS en producción.

## Cierre de sesión

Documentar comandos exactos y nombres de bindings. WORKER-002 debe trabajar dentro de este esqueleto sin cambiar la arquitectura.

## Cierre de WORKER-001 — 2026-07-18

Se creó en la raíz del proyecto un único Cloudflare Worker TypeScript en
formato ES Modules, gestionado únicamente con pnpm. No se implementó ninguna
lógica PREVIFOC ni parte de WORKER-002.

### Arquitectura y rutas provisionales

`wrangler.jsonc` fija `compatibility_date = 2026-07-18` y las decisiones del
ticket:

- Static Assets en `./public` mediante el binding `ASSETS`;
- KV mediante `PREVIFOC_STATE`;
- Cron Trigger UTC exacto `7 * * * *`;
- ejecución previa del Worker solo para `/health`, `/status.json` y
  `/tiles/*`; los demás assets conservan el enrutado asset-first;
- IDs KV no sensibles de placeholder: producción
  `00000000000000000000000000000000` y preview
  `11111111111111111111111111111111`.

Los placeholders permiten desarrollo local y dry run, pero deben sustituirse
por los IDs de dos namespaces creados explícitamente antes de cualquier
despliegue real. No se creó ningún namespace y no se leyó ni escribió KV
remoto.

`src/index.ts` implementa handlers mínimos:

- `/health`: JSON 200 y `no-store`;
- `/status.json`: estado `scaffold`, 9.507 teselas y `geometry_version`
  congelada;
- `/tiles/{z}/{x}/{y}.png`: entrega el asset exacto y reutiliza
  `transparent.png` si una XYZ válida z6–14 no tiene cobertura;
- resto: delegación a `ASSETS`;
- `scheduled()`: solo registra un evento con `effects: "none"`; no hace red,
  no descarga PREVIFOC y no escribe KV.

La página `static/index.html` es deliberadamente un marcador técnico, no la
página pública final de WEB-001.

### Staging inmutable y guardas

`scripts/stage-assets.mjs` genera el directorio ignorado `public/` desde
`data/tiles-002/` sin escribir en la fuente. Antes de copiar exige:

- `geometry_version`:
  `sha256:e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0`;
- `manifest.json`:
  `5534833f228772b4e25602420cdc51024603b6971d8a58c5ab590649dd8a1972`;
- `tiles.sha256`:
  `4fd05f73854d7cb620aa1d2721096b54dd1217f29c514f3242448febdb9f1bc0`;
- `transparent.png`:
  `00af44e300322d960f89aaa5dac93b0517fd1625ec0c058f3212661276a0d0ba`;
- exactamente 9.507 líneas/rutas cubiertas y 4.603.224 bytes de teselas.

Cada PNG se vuelve a verificar contra el inventario antes de copiarlo. El
staging final tiene 9.509 ficheros: 9.507 teselas cubiertas, un
`transparent.png` y un `index.html`; ocupa exactamente 4.603.776 bytes. La
guarda falla con 19.000 assets o más. `scripts/check-bundle.mjs` aplica además
una guarda propia de 1 MiB al JavaScript empaquetado.

Wrangler mostró `Read 9719 files`; el conteo independiente de ficheros
regulares es 9.509 y existen 210 directorios bajo `public/` (9.509 + 210 =
9.719). El límite de assets y la guarda se aplican a los ficheros publicables,
no a directorios.

### Versiones y tipado

Entorno verificado:

| Componente | Versión |
|---|---:|
| Node.js | 24.6.0 |
| pnpm | 10.18.1 |
| Wrangler | 4.112.0 |
| workerd de tipos/runtime local | 1.20260714.1 |
| TypeScript | 7.0.2 |
| Vitest | 4.1.10 |
| `@cloudflare/vitest-pool-workers` | 0.18.6 |

`pnpm-lock.yaml` fija el árbol instalado. `wrangler types` generó
`worker-configuration.d.ts`; su interfaz contiene exactamente
`PREVIFOC_STATE: KVNamespace` y `ASSETS: Fetcher`. No hay `dependencies` de
producción: todas las herramientas son `devDependencies`, y no se incorporó
framework HTTP, servidor Node, Fastify, R2, D1, Cloudflare Images ni binarios
GIS.

### Comandos y resultados exactos

Desde la raíz del proyecto:

```sh
pnpm install
pnpm cf-typegen
pnpm typecheck
WRANGLER_LOG_PATH=/tmp/worker001-wrangler-test-final.log pnpm test
WRANGLER_LOG_PATH=/tmp/worker001-wrangler-dev.log \
  pnpm exec wrangler dev --test-scheduled --ip 127.0.0.1 --port 8787
curl --fail --silent --show-error --include http://127.0.0.1:8787/health
curl --fail --silent --show-error --include http://127.0.0.1:8787/index.html
curl --fail --silent --show-error --include \
  http://127.0.0.1:8787/tiles/6/31/24.png
curl --fail --silent --show-error --include \
  'http://127.0.0.1:8787/__scheduled?cron=7+*+*+*+*'
WRANGLER_LOG_PATH=/tmp/worker001-wrangler-dry-run-final.log \
  pnpm deploy:dry-run
pnpm check:assets
```

Resultados:

- `pnpm install`: código 0;
- `pnpm cf-typegen`: tipos de proyecto y runtime generados;
- `pnpm typecheck`: código 0 para fuente y tests;
- `pnpm test`: 1 fichero y 3 tests correctos dentro de workerd;
- `/health`: 200 JSON desde el Worker;
- `/index.html`: 200 `text/html` desde Static Assets;
- `/tiles/6/31/24.png`: 200 `image/png`, 1.119 bytes y SHA-256
  `b063e13960a4ca08ada1f4b7b3569ed268b01089af1b4664ecbf15162cf1b72d`;
- `__scheduled`: 200 `Ran scheduled event`; el log registra cron exacto y
  `effects: "none"`;
- dry run: código 0, `Total Upload: 2.82 KiB / gzip: 1.16 KiB`, bundle
  JavaScript exacto de 2.887 bytes frente a la guarda de 1.048.576 bytes;
- `pnpm check:assets`: 9.509 assets, 9.507 cubiertos y 4.603.224 bytes de
  teselas, código 0.

El sandbox ordinario impedía que workerd/`wrangler types` abrieran un socket
en `127.0.0.1` y que Wrangler escribiera su log en preferencias de usuario.
Las pruebas se repitieron con socket local autorizado y
`WRANGLER_LOG_PATH` bajo `/tmp`; pasaron. No queda un bloqueo para el dry run.

No se intentó un despliegue real, conforme a la prohibición de hacerlo sin
autorización explícita. Además de esa autorización, el despliegue real requiere
autenticación Cloudflare y sustituir ambos IDs KV placeholder por namespaces
reales.

### Documentación oficial contrastada

Revisada el 2026-07-18:

- [Wrangler configuration](https://developers.cloudflare.com/workers/wrangler/configuration/);
- [Static Assets: binding y `run_worker_first`](https://developers.cloudflare.com/workers/static-assets/binding/);
- [límites de Workers y Static Assets](https://developers.cloudflare.com/workers/platform/limits/);
- [Workers KV: bindings y desarrollo local](https://developers.cloudflare.com/kv/get-started/);
- [Cron Trigger y prueba con Wrangler](https://developers.cloudflare.com/workers/examples/cron-trigger/);
- [handler `scheduled()`](https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/);
- [integración Vitest para Workers](https://developers.cloudflare.com/workers/testing/vitest-integration/);
- [primera prueba y generación de tipos](https://developers.cloudflare.com/workers/testing/vitest-integration/write-your-first-test/);
- [API de tests, incluido `createScheduledController`](https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/);
- [dry run y `--outdir`](https://developers.cloudflare.com/workers/wrangler/commands/workers/);
- [bundling de Wrangler](https://developers.cloudflare.com/workers/wrangler/bundling/).

### Integridad de dependencias anteriores

Antes y después del trabajo se comparó una instantánea SHA-256 de 9.548
ficheros bajo `data/tiles-002`, las entradas/salidas GEO, TILES-001 y
`deploy/osmand-001`; `cmp` terminó con código 0. TILES-002 no se regeneró,
modificó, sustituyó, recoloreó ni sobrescribió: solo se leyó y se copió a un
staging reproducible ignorado.

Se confirma expresamente que TILES-002, GEO, OSMAND-001 y la infraestructura
temporal de publicación no fueron modificados. Tampoco se reabrió ni modificó
OSMAND-002, no se escribió KV y no se inició WORKER-002 ni ningún ticket
posterior.
