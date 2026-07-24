# WORKER-003 — Publicar y gestionar el estado actual en KV

**Estado:** completado  
**Dependencias:** [WORKER-002](./WORKER-002-ingesta-previfoc.md)  
**Siguiente:** [WORKER-004](./WORKER-004-recoloreado-cache.md)

## Objetivo

Conectar la ingesta validada con el Cron horario y mantener en KV un único estado completo, determinista y seguro ante fallos.

## Estado persistido

La clave `current` contiene `schemaVersion`, `snapshotId`, timestamps y las siete zonas. `snapshotId` es SHA-256 de la fecha fuente y los niveles ordenados por ID.

La obsolescencia no se persiste: se calcula al leer comparando la fecha fuente con la fecha actual en `Europe/Madrid`.

## Alcance

- Ejecutar la ingesta desde `scheduled()` cada hora.
- Escribir KV únicamente después de validar el candidato completo.
- No escribir si el hash semántico coincide con el estado actual; actualizar solo métricas/logs de recuperación.
- Conservar el último estado válido ante timeout, error HTTP o esquema incompatible.
- Implementar lectura tipada y compatibilidad explícita de `schemaVersion`.
- Exponer `/status.json` y `/health`.
- Calcular correctamente cambio de día y horario de verano.

## Contratos HTTP

- `/status.json`: 200 con estado e `isStale`; 503 JSON si nunca hubo estado válido; caché pública máxima cinco minutos.
- `/health`: 200 solo con dato del día; 503 si está ausente u obsoleto; `no-store`.

## Fuera de alcance

- Servir teselas coloreadas.
- Historial de snapshots.
- Alertas externas.
- Edición manual del estado en producción.

## Entregables

- Handler horario completo.
- Repositorio KV tipado.
- Rutas de estado y salud.
- Pruebas con KV aislado.

## Criterios de aceptación

- [x] Un candidato válido se guarda de forma completa bajo `current`.
- [x] Un candidato inválido no cambia KV.
- [x] El mismo estado genera siempre el mismo `snapshotId`.
- [x] Un cambio en cualquier nivel genera otro snapshot.
- [x] A medianoche de Madrid, el estado del día anterior pasa a obsoleto sin esperar al cron.
- [x] Las pruebas cubren CET y CEST.
- [x] `/health` diferencia actual, obsoleto y nunca disponible.
- [x] No se guarda `npre` ni geometría en KV.

## Cierre de sesión

Documentar un ejemplo real anonimizado de `/status.json`. WORKER-004 lo usará como único contrato de color.

## Cierre de WORKER-003 — 2026-07-18

Se conectó `ingestCurrentStateCandidate()` al handler `scheduled()` horario y
se añadió `src/state.ts` como única frontera de persistencia. La promoción
valida otra vez el candidato completo antes de leer o escribir KV. La única
clave admitida es `current`; no existe historial, clave auxiliar ni métrica
persistida.

### Esquema exacto de `current`

El valor es un JSON estricto de versión 1. No se aceptan campos adicionales en
el objeto raíz, procedencia o zonas:

```text
object
├── schemaVersion: 1
├── snapshotId: "sha256:" + 64 hex minúsculas
├── sourceTimestampOriginal: "YYYY-MM-DD HH:mm:ss[.SSS]"
├── retrievedAt: string ISO 8601 UTC canónica
├── publishedAt: string ISO 8601 UTC canónica
├── provenance
│   ├── previfoc
│   │   ├── source: "previfoc"
│   │   ├── requestedUrl: URL HTTP(S)
│   │   ├── responseUrl: URL HTTP(S)
│   │   ├── retrievedAt: string ISO 8601 UTC canónica
│   │   └── attempts: 1 | 2
│   └── situacion: mismos campos, source = "situacion"
└── zones: array de longitud 7, orden exacto 53–59
    └── { zoneId, situationId, level, forestAccess }
```

Cada zona exige que `situationId` esté en 1–9, que `level` corresponda a la
traducción validada de WORKER-002 y que `forestAccess` sea
`closed_by_mvp_rule` solo para nivel 3. Al leer se vuelve a calcular y comparar
el hash; JSON inválido, forma incompatible, hash incoherente o una
`schemaVersion` distinta se rechazan explícitamente. Un valor incompatible ya
existente no se sobrescribe con la versión 1.

La serialización canónica que alimenta SHA-256 es exactamente:

```json
{"sourceDate":"2026-07-18","levels":[[53,2],[54,2],[55,2],[56,3],[57,2],[58,3],[59,2]]}
```

Solo intervienen la fecha civil fuente y los pares `zoneId`/`level` ya
ordenados. `retrievedAt`, `publishedAt`, procedencia y cambios de
`situationId` que permanecen dentro del mismo nivel no cambian la identidad
semántica. El digest se calcula con `crypto.subtle.digest("SHA-256", ...)` y el
ejemplo anterior produjo
`sha256:2542366c8bfa830253174262d41d7855d64f36a2e85cdc47e7ccde45fa308588`.

Si coincide con el estado validado actual, no se llama a `KV.put`; la
recuperación solo emite el resultado seguro `unchanged`. Una ingesta o
persistencia fallida deja intactos los bytes del último valor válido.

### Obsolescencia y contratos HTTP

`isStale` no existe en KV. En cada lectura se extrae la fecha original y se
compara con la fecha civil del reloj actual obtenida mediante
`Intl.DateTimeFormat` con `timeZone: "Europe/Madrid"`, calendario ISO y dígitos
latinos. No hay offset CET/CEST codificado. Las pruebas fijan los cambios de día
de invierno a las 23:00 UTC y de verano a las 22:00 UTC, además del instante
exacto de medianoche.

- `/status.json`: `200` con el estado completo y `isStale` cuando `current` es
  válido; `503` JSON si falta o no puede leerse con seguridad;
  `Cache-Control: public, max-age=300` en ambos casos.
- `/health`: `200` solo cuando la fecha fuente coincide con el día de Madrid;
  `503` si falta, está obsoleta o es incompatible; siempre
  `Cache-Control: no-store`.
- `/tiles/*` conserva validación XYZ, entrega directa del asset cubierto y
  fallback al `transparent.png` congelado. El resto continúa delegado a
  `ASSETS`.

Ejemplo real anonimizado de `/status.json`, obtenido del ciclo local del
2026-07-18. Se sustituyeron únicamente las URLs públicas por `example.invalid`
y se abrevia la procedencia repetitiva; fecha, niveles y `snapshotId` son los
observados:

```json
{
  "schemaVersion": 1,
  "snapshotId": "sha256:2542366c8bfa830253174262d41d7855d64f36a2e85cdc47e7ccde45fa308588",
  "sourceTimestampOriginal": "2026-07-18 17:05:48.0",
  "retrievedAt": "2026-07-18T15:30:53.940Z",
  "publishedAt": "2026-07-18T15:30:53.943Z",
  "provenance": {
    "previfoc": {
      "source": "previfoc",
      "requestedUrl": "https://example.invalid/previfoc",
      "responseUrl": "https://example.invalid/previfoc",
      "retrievedAt": "2026-07-18T15:30:53.940Z",
      "attempts": 1
    },
    "situacion": {
      "source": "situacion",
      "requestedUrl": "https://example.invalid/situacion",
      "responseUrl": "https://example.invalid/situacion",
      "retrievedAt": "2026-07-18T15:30:53.938Z",
      "attempts": 1
    }
  },
  "zones": [
    {"zoneId":53,"situationId":5,"level":2,"forestAccess":"no_closure_inferred"},
    {"zoneId":54,"situationId":5,"level":2,"forestAccess":"no_closure_inferred"},
    {"zoneId":55,"situationId":4,"level":2,"forestAccess":"no_closure_inferred"},
    {"zoneId":56,"situationId":8,"level":3,"forestAccess":"closed_by_mvp_rule"},
    {"zoneId":57,"situationId":4,"level":2,"forestAccess":"no_closure_inferred"},
    {"zoneId":58,"situationId":8,"level":3,"forestAccess":"closed_by_mvp_rule"},
    {"zoneId":59,"situationId":4,"level":2,"forestAccess":"no_closure_inferred"}
  ],
  "isStale": false
}
```

### Cron, fallos y logs

Se conserva el trigger UTC `7 * * * *`. El handler espera la ingesta y la
promoción completas. En éxito registra solo `event`, `outcome` (`published` o
`unchanged`), cron configurado/recibido y hora programada. En fallo registra
`preserved_last_valid`, código tipado y, si procede, nombre de fuente. Nunca
incluye mensajes de excepción, cuerpos HTTP, catálogo, zonas, HTML ni tokens.

Las pruebas inyectan timeout/red (`FETCH_FAILED`), HTTP, catálogo incompatible,
candidato incompleto y versión KV incompatible. En todos esos casos comparan
los bytes de `current` o acreditan que `put()` no fue invocado. También prueban
que no se persisten `npre`, descripciones HTML, tormenta seca, geometría ni
`isStale`.

Workers KV es eventualmente consistente. Una escritura es inmediata en la
misma ubicación, pero Cloudflare documenta hasta 60 segundos para otras
ubicaciones y un máximo de una escritura por segundo sobre la misma clave. El
Cron único horario y la supresión por hash reducen escrituras; WORKER-003 no
añade Durable Objects ni coordinación distribuida fuera de alcance.

### Verificación y evidencia

Versiones observadas:

| Componente | Versión |
|---|---:|
| Node.js | 24.6.0 |
| pnpm | 10.18.1 |
| Wrangler | 4.112.0 |
| workerd | 1.20260714.1 |
| TypeScript | 7.0.2 |
| Vitest | 4.1.10 |
| `@cloudflare/vitest-pool-workers` | 0.18.6 |

Comandos exactos ejecutados desde la raíz:

```sh
pnpm install
pnpm typecheck
WRANGLER_LOG_PATH=/tmp/worker003-wrangler-test.log pnpm test
pnpm check:assets
WRANGLER_LOG_PATH=/tmp/worker003-wrangler-dry-run.log pnpm deploy:dry-run
```

Resultados finales: typecheck código 0; **3 ficheros y 38 pruebas** correctas
dentro de workerd; 9.509 assets, 9.507 teselas cubiertas y 4.603.224 bytes de
teselas; dry run código 0, `Total Upload: 26.69 KiB / gzip: 6.62 KiB` y bundle
de 27.328 bytes frente a la guarda de 1 MiB. `wrangler.jsonc` no cambió, por lo
que no se ejecutó `pnpm cf-typegen` ni cambió
`worker-configuration.d.ts`.

La comprobación HTTP utilizó persistencia efímera explícita fuera del
repositorio y se detuvo limpiamente:

```sh
WRANGLER_LOG_PATH=/tmp/worker003-wrangler-dev.log \
  pnpm exec wrangler dev --test-scheduled --local \
  --persist-to /tmp/worker003-wrangler-state.RhTdlz \
  --ip 127.0.0.1 --port 8789 --inspector-port 9231 \
  --show-interactive-dev-session false
curl --silent --show-error --include http://127.0.0.1:8789/health
curl --silent --show-error --include http://127.0.0.1:8789/status.json
curl --silent --show-error --include http://127.0.0.1:8789/index.html
curl --silent --show-error --include \
  'http://127.0.0.1:8789/__scheduled?cron=7+*+*+*+*'
```

Antes del evento, salud y estado devolvieron 503 y el asset 200. El primer
evento consultó ambas fuentes públicas, publicó únicamente en KV local y
registró `published`; salud/estado pasaron a 200. La segunda invocación registró
`unchanged`. No se creó una ruta de diagnóstico. El sandbox ordinario bloqueó
el socket local de workerd; la repetición autorizada pasó. No queda bloqueo
técnico.

### Documentación oficial contrastada

Consultada el 2026-07-18:

- [Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/)
  y [handler programado](https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/);
- [Workers KV](https://developers.cloudflare.com/kv/),
  [lectura](https://developers.cloudflare.com/kv/api/read-key-value-pairs/),
  [escritura](https://developers.cloudflare.com/kv/api/write-key-value-pairs/)
  y [modelo de consistencia](https://developers.cloudflare.com/kv/concepts/how-kv-works/);
- [Web Crypto en Workers](https://developers.cloudflare.com/workers/runtime-apis/web-crypto/)
  y [estándares JavaScript/Intl](https://developers.cloudflare.com/workers/runtime-apis/web-standards/);
- [configuración Wrangler](https://developers.cloudflare.com/workers/wrangler/configuration/)
  y [comandos `dev`/`deploy --dry-run`](https://developers.cloudflare.com/workers/wrangler/commands/workers/);
- [integración oficial Vitest](https://developers.cloudflare.com/workers/testing/vitest-integration/),
  [API de tests](https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/)
  y [aislamiento](https://developers.cloudflare.com/workers/testing/vitest-integration/isolation-and-concurrency/);
- [ECMA-402 edición 2026](https://402.ecma-international.org/) e
  [IANA Time Zone Database](https://www.iana.org/time-zones).

### Bindings, integridad y alcance

Siguen existiendo exactamente `PREVIFOC_STATE: KVNamespace` y
`ASSETS: Fetcher`, con los IDs placeholder heredados y el Cron UTC original.
No se creó namespace, infraestructura o despliegue; no se accedió a KV remoto.
La única escritura externa al proceso fue al KV local aislado de Vitest o de
Wrangler bajo `/tmp`.

Se confirma expresamente que TILES-002, todas las entradas/salidas GEO,
OSMAND-001, OSMAND-002, WORKER-001, WORKER-002 y la infraestructura temporal
heredada no fueron modificados. TILES-002 solo se leyó y copió mediante el
staging reproducible; no se regeneró, sustituyó, recoloreó ni sobrescribió.
Permanecen 9.507 teselas y las huellas congeladas de `manifest.json`,
`tiles.sha256` y `transparent.png`. No se inició WORKER-004 ni ningún ticket
posterior.
