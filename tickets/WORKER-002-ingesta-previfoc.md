# WORKER-002 — Obtener y validar el estado PREVIFOC actual

**Estado:** completado  
**Dependencias:** [WORKER-001](./WORKER-001-scaffold-cloudflare.md)  
**Siguiente:** [WORKER-003](./WORKER-003-estado-kv.md)

## Objetivo

Implementar una función pura y probada que descargue `previfoc` y `situacion`, resuelva `nact` y produzca el estado actual normalizado de las siete zonas.

## Contexto

`nact` referencia una situación y no es directamente el nivel. Solo se aceptan situaciones activas con `ID_AVISO = 3`. `npre` y la tormenta seca no forman parte del MVP visual.

Leer antes: [DATA_SOURCES.md](../DATA_SOURCES.md).

## Alcance

- Descargar ambas fuentes en paralelo mediante `fetch`.
- Aplicar timeout con `AbortSignal` y un reintento acotado ante fallos transitorios.
- Validar forma, tipos, IDs, estado activo y relaciones.
- Exigir exactamente los IDs de zona 53–59.
- Traducir situaciones 1–3 a nivel 1, 4–6 a nivel 2 y 7–9 a nivel 3, validando siempre el catálogo.
- Producir tipos internos estables y conservar timestamp original, recuperación y procedencia.
- Calcular `forestAccess`: nivel 3 `closed_by_mvp_rule`; niveles 1/2 `no_closure_inferred`.

## Fuera de alcance

- KV, caché o rutas HTTP públicas.
- Previsión de mañana.
- Mostrar tormentas secas.
- Consultar resoluciones jurídicas.

## Entregables

- Adaptadores/validadores de las dos fuentes.
- Tipo `CurrentStateCandidate`.
- Fixtures válidos e inválidos.
- Suite de pruebas de traducción.

## Criterios de aceptación

- [x] Se producen exactamente siete zonas ordenadas por ID.
- [x] Cada `nact` resuelve una situación activa de PREVIFOC.
- [x] Los nueve IDs de situación se traducen al nivel esperado.
- [x] Un ID desconocido, duplicado o de otro aviso invalida el candidato completo.
- [x] Campos adicionales compatibles no rompen la ingesta.
- [x] Ausencia o cambio de tipo en un campo obligatorio sí la rompe.
- [x] Nivel 3 aplica la regla conservadora y nivel 1/2 nunca se denomina “abierto”.
- [x] Los errores no contienen cuerpos completos ni datos innecesarios en logs.

## Cierre de sesión

Entregar una función sin efectos de almacenamiento. WORKER-003 decidirá cuándo un candidato puede sustituir el estado publicado.

## Cierre de WORKER-002 — 2026-07-18

Se implementó la ingesta y normalización en `src/previfoc.ts`, aislada del
handler del Worker. `scheduled()` conserva deliberadamente `effects: "none"`:
WORKER-002 ofrece el candidato validado, pero WORKER-003 sigue siendo el único
ticket autorizado para decidir su promoción y escribir KV.

### Contrato interno y validación

`CurrentStateCandidate` conserva:

- `sourceTimestampOriginal`, sin atribuir zona horaria no documentada al valor
  de `previfoc.time`;
- `retrievedAt` y procedencia separada de ambas respuestas, con fuente, URL
  solicitada/final, instante de recuperación y uno o dos intentos;
- exactamente siete `CurrentZoneState`, ordenados 53–59, con
  `situationId`, `level` y `forestAccess`.

Los adaptadores exigen objeto/array y los campos obligatorios usados por el
MVP: `previfoc.time`, `previfoc.z1[].id`, `previfoc.z1[].nact`,
`situacion.SITUACION[].ID_SITUACION`, `ID_AVISO` y `ACTIVO`. Los valores no
consumidos, incluido `npre`, descripciones HTML y tormenta seca, no se copian al
candidato. Campos adicionales son compatibles.

El catálogo se valida completo antes de resolver ninguna zona: IDs 1–9 una
sola vez, `ID_AVISO = 3` y `ACTIVO = "S"`. Filas 10–17 de otros avisos son
compatibles, como en la fuente oficial, pero reutilizar 1–9 para otro aviso,
añadir un ID PREVIFOC desconocido, duplicar cualquier ID o dejar incompleto el
catálogo invalida el candidato entero. La traducción fijada es 1–3 → nivel 1,
4–6 → nivel 2 y 7–9 → nivel 3.

La salida usa únicamente `closed_by_mvp_rule` para nivel 3 y
`no_closure_inferred` para niveles 1/2; nunca afirma que el acceso esté
“abierto”.

### Descarga y tratamiento de fallos

`ingestCurrentStateCandidate()` inicia ambos `fetch` mediante `Promise.all`.
Cada fuente tiene timeout total predeterminado de 5.000 ms, incluido el consumo
del cuerpo, mediante `AbortController`; aplica como máximo dos intentos con una
espera acotada predeterminada de 200 ms. Solo reintenta errores de red/timeout y
HTTP 408, 425, 429 o 5xx. Un 4xx restante, MIME distinto de JSON, JSON inválido
o esquema inválido falla sin reintentar datos que no son transitorios.

`PrevifocIngestionError` expone código y nombre de fuente, pero no propaga el
texto de excepciones de red, cuerpos HTTP, HTML, tokens ni valores completos.
La librería no escribe en consola. Las opciones inyectables de `fetch`, reloj,
espera, timeout y URLs permiten pruebas deterministas sin crear una ruta de
diagnóstico ni efectos persistentes.

### Fixtures y cobertura

`test/fixtures/previfoc.ts` contiene fixtures completos válidos y dos inválidos
con zona duplicada y situación asignada a otro aviso. Las pruebas adicionales
generan de forma aislada casos de zona ausente/desconocida, `nact` desconocido,
catálogo incompleto/inactivo/desconocido/duplicado, campos obligatorios ausentes
o con tipo cambiado, campos adicionales, errores HTTP, red, timeout de
cabeceras y cuerpo, JSON inválido y redacción.

La suite final pasa **2 ficheros y 18 pruebas** dentro de workerd: las 15 de
WORKER-002 y las 3 heredadas de WORKER-001. También comprueba que
`PREVIFOC_STATE` permanece vacío después del evento programado.

### Contraste de fuentes vigente

El 2026-07-18 se recuperaron una vez los dos endpoints oficiales con
`User-Agent: OsmAnd-Incendios-WORKER-002/1.0 (schema validation)`, sin guardar
los cuerpos en el repositorio:

- `previfoc`: HTTP 200, `application/json`, 1.960 bytes,
  `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` y tiempo
  original `2026-07-18 00:01:41.0`;
- `situacion`: HTTP 200, `application/json`, 3.710 bytes y
  `Cache-Control: public, max-age=43200`;
- la normalización exacta de esas respuestas produjo zonas 53–59, situaciones
  `[5, 5, 4, 8, 4, 8, 4]` y niveles `[2, 2, 2, 3, 2, 3, 2]`.

La normalización en vivo se ejecutó sin publicar una ruta temporal:

```sh
pnpm exec esbuild src/previfoc.ts --bundle --platform=node --format=esm \
  --outfile=/tmp/worker002-previfoc.mjs
node --input-type=module -e \
  'import { readFileSync } from "node:fs"; import("file:///tmp/worker002-previfoc.mjs").then((m) => { const p = JSON.parse(readFileSync("/tmp/worker002-previfoc.json", "utf8")); const s = JSON.parse(readFileSync("/tmp/worker002-situacion.json", "utf8")); const at = "2026-07-18T15:00:00.000Z"; const source = (name, url) => ({ source: name, requestedUrl: url, responseUrl: url, retrievedAt: at, attempts: 1 }); const c = m.normalizeCurrentStateCandidate(p, s, { previfoc: source("previfoc", m.PREVIFOC_URL), situacion: source("situacion", m.SITUACION_URL) }); console.log(JSON.stringify({ sourceTimestampOriginal: c.sourceTimestampOriginal, zoneIds: c.zones.map((z) => z.zoneId), situationIds: c.zones.map((z) => z.situationId), levels: c.zones.map((z) => z.level), forestAccess: c.zones.map((z) => z.forestAccess) })); });'
```

La página oficial de incendios devolvía “Aplicación fuera de servicio” durante
la revisión web, pero ambos endpoints estructurados respondieron correctamente
por HTTPS. Se mantiene la limitación ya documentada: no existe contrato público
de API, SLA, licencia de reutilización, zona horaria formal de `time` ni
semántica publicada de los campos no usados.

Documentación oficial contrastada el 2026-07-18:

- [Incendios forestales — 112CV](https://www.112cv.gva.es/es/incendios-forestales);
- [`previfoc`](https://wpr.112cv.gva.es/external/api/storage/descargar/json/previfoc)
  y [`situacion`](https://wpr.112cv.gva.es/external/api/storage/descargar/json/static/situacion);
- [Fetch en Workers](https://developers.cloudflare.com/workers/runtime-apis/fetch/),
  [Request `signal`](https://developers.cloudflare.com/workers/runtime-apis/request/)
  y [Web Standards](https://developers.cloudflare.com/workers/runtime-apis/web-standards/);
- [esperas y reintentos acotados](https://developers.cloudflare.com/workers/runtime-apis/scheduler/);
- [Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/);
- [Workers KV](https://developers.cloudflare.com/kv/) y
  [escritura KV](https://developers.cloudflare.com/kv/api/write-key-value-pairs/);
- [configuración Wrangler](https://developers.cloudflare.com/workers/wrangler/configuration/),
  [comandos y `--dry-run`](https://developers.cloudflare.com/workers/wrangler/commands/workers/)
  y [bundling](https://developers.cloudflare.com/workers/wrangler/bundling/);
- [integración Vitest](https://developers.cloudflare.com/workers/testing/vitest-integration/),
  [API de tests](https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/)
  y [recetas de mocks](https://developers.cloudflare.com/workers/testing/vitest-integration/recipes/).

### Entorno, bindings y comandos exactos

| Componente | Versión |
|---|---:|
| Node.js | 24.6.0 |
| pnpm | 10.18.1 |
| Wrangler | 4.112.0 |
| workerd | 1.20260714.1 |
| TypeScript | 7.0.2 |
| Vitest | 4.1.10 |
| `@cloudflare/vitest-pool-workers` | 0.18.6 |

No cambió `wrangler.jsonc`; por tanto no fue necesario regenerar
`worker-configuration.d.ts` con `pnpm cf-typegen`. Siguen existiendo exactamente
los bindings `ASSETS: Fetcher` y `PREVIFOC_STATE: KVNamespace`, el Cron UTC
`7 * * * *` y los placeholders KV de WORKER-001. No se añadió ninguna
dependencia ni script y `pnpm-lock.yaml` permaneció igual.

Comandos de instalación, fuentes, compilación y pruebas:

```sh
pnpm install
curl --fail --silent --show-error --location --connect-timeout 10 --max-time 60 \
  --user-agent 'OsmAnd-Incendios-WORKER-002/1.0 (schema validation)' \
  --dump-header /tmp/worker002-previfoc.headers \
  --output /tmp/worker002-previfoc.json \
  https://wpr.112cv.gva.es/external/api/storage/descargar/json/previfoc
curl --fail --silent --show-error --location --connect-timeout 10 --max-time 60 \
  --user-agent 'OsmAnd-Incendios-WORKER-002/1.0 (schema validation)' \
  --dump-header /tmp/worker002-situacion.headers \
  --output /tmp/worker002-situacion.json \
  https://wpr.112cv.gva.es/external/api/storage/descargar/json/static/situacion
pnpm typecheck
WRANGLER_LOG_PATH=/tmp/worker002-wrangler-test-final.log pnpm test
```

La comprobación local del runtime se realizó y se detuvo limpiamente:

```sh
WRANGLER_LOG_PATH=/tmp/worker002-wrangler-dev.log \
  pnpm exec wrangler dev --test-scheduled --ip 127.0.0.1 --port 8788
curl --fail --silent --show-error --include http://127.0.0.1:8788/health
curl --fail --silent --show-error --include http://127.0.0.1:8788/index.html
curl --fail --silent --show-error --include \
  'http://127.0.0.1:8788/__scheduled?cron=7+*+*+*+*'
```

Los tres endpoints devolvieron 200; el log del Cron conservó
`effects: "none"`. La respuesta `/health` todavía dice `phase: "WORKER-001"`
porque cambiar rutas públicas queda fuera de WORKER-002.

Comandos finales de empaquetado y staging:

```sh
WRANGLER_LOG_PATH=/tmp/worker002-wrangler-dry-run.log pnpm deploy:dry-run
pnpm check:assets
```

Resultados: dry run código 0, `Total Upload: 2.82 KiB / gzip: 1.16 KiB`,
bundle de 2.887 bytes frente a la guarda de 1 MiB; staging de 9.509 assets,
9.507 teselas cubiertas y 4.603.224 bytes de teselas, por debajo de 19.000.
Wrangler no incluye todavía `src/previfoc.ts` en el bundle porque ningún handler
lo importa; esto es deliberado para no adelantar la conexión programada de
WORKER-003. TypeScript y las pruebas workerd sí compilan y ejecutan el módulo.
No se desplegó nada.

### Bloqueos e integridad heredada

El sandbox ordinario volvió a impedir el socket `127.0.0.1` de workerd; la
suite se repitió con el permiso local ya requerido por WORKER-001 y pasó. La
primera consulta local a Wrangler ocurrió antes de que el servidor indicara
`Ready`; se repitió después y los tres controles pasaron. No queda un bloqueo
técnico.

Se compararon antes y después huellas SHA-256 de los 9.515 ficheros de
`data/tiles-002`, todas las entradas/salidas GEO, TILES-001, la evidencia
OSMAND-002 y `deploy/osmand-001`; ambos `cmp` terminaron con código 0. Los hashes
inmutables de `manifest.json`, `tiles.sha256` y `transparent.png` siguen siendo
respectivamente `5534833f228772b4e25602420cdc51024603b6971d8a58c5ab590649dd8a1972`,
`4fd05f73854d7cb620aa1d2721096b54dd1217f29c514f3242448febdb9f1bc0`
y `00af44e300322d960f89aaa5dac93b0517fd1625ec0c058f3212661276a0d0ba`.

Los inventarios de integridad se construyeron con:

```sh
find data/tiles-002 data/zones data/crosswalk data/sources data/geo-004 \
  data/tiles-001 data/osmand-002 deploy/osmand-001 -type f -print0 \
  | sort -z | xargs -0 shasum -a 256 \
  > /tmp/worker002-all-protected-before.sha256
# Repetido al final con destino worker002-all-protected-after.sha256.
cmp /tmp/worker002-all-protected-before.sha256 \
  /tmp/worker002-all-protected-after.sha256
```

Se confirma expresamente que TILES-002, GEO, OSMAND-001, OSMAND-002,
WORKER-001 y la infraestructura temporal no fueron modificados. TILES-002 se
leyó y copió únicamente mediante el staging reproducible heredado; no se
regeneró, sustituyó, recoloreó ni sobrescribió. No se accedió a KV remoto ni se
escribió KV, no se crearon namespaces, no se cambió infraestructura y no se
inició WORKER-003, WORKER-004 ni ningún ticket posterior. La única lectura KV
fue el `list()` del namespace local aislado que la prueba heredada usa para
acreditar que sigue vacío.
