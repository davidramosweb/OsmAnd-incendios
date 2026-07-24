# RELEASE-001 — Despliegue y estado de aceptación

## Recursos activos

- Fecha del primer despliegue: 2026-07-18.
- Worker: `previfoc-osmand`.
- Dominio: `https://previfoc.davidramosweb.com`.
- URL workers.dev: `https://previfoc-osmand.quiet-mountain-f8dd.workers.dev`.
- Versión activa: `578e178b-7544-41a9-9475-cd063929f08c`.
- Versión anterior recuperable: `c9ff2a89-6e1d-4d7e-b91f-520e95496e2c`.
- KV producción: `855480b5380e47b1881e1f178c6a92e7`.
- KV preview: `3584deea553c46d29ddcde14661506d6`.
- Cron: `7 * * * *` UTC.
- Assets publicados: 9.512 ficheros; 9.507 teselas cubiertas.

Las credenciales OAuth de Wrangler permanecen en el almacén local del usuario
y no se copiaron al repositorio.

## Primera captura

La fuente actual se descargó una vez y pasó
`ingestCurrentStateCandidate`, `calculateSnapshotId` y
`validatePersistedCurrentState`. El JSON canónico se escribió como clave
`current` del KV de producción y el generador temporal fue retirado después.
No se añadió una ruta de administración y no se modificó el cron horario.

- fecha/hora fuente: `2026-07-18 17:05:48.0`;
- snapshot:
  `sha256:2542366c8bfa830253174262d41d7855d64f36a2e85cdc47e7ccde45fa308588`;
- niveles: `53:2, 54:2, 55:2, 56:3, 57:2, 58:3, 59:2`;
- zonas 56 y 58: `closed_by_mvp_rule`;
- resto: `no_closure_inferred`.

## Matriz HTTPS observada

| Ruta | HTTP | Resultado |
|---|---:|---|
| `/` | 200 | HTML final con estado, leyenda, atribución y aviso. |
| `/health` | 200 | `ok: true`, `status: current`, fecha Madrid 2026-07-18. |
| `/status.json` | 200 | Siete zonas, snapshot anterior, `isStale: false`. |
| `/previfoc.osf` | 200 | 1.792 bytes; hash `dab5d3cf…85ec7`; descarga binaria y `nosniff`. |
| `/tiles/6/31/24.png` | 200 | PNG dinámico; hash `d82b132f…556f9`; estado no obsoleto. |
| `/index%202.html` | 404 | El scaffold provisional no forma parte del manifiesto público. |

La tesela lleva `ETag` ligado al snapshot,
`x-previfoc-snapshot` y `x-previfoc-stale: false`. Antes de publicar el primer
estado, la misma ruta respondió con el PNG gris seguro y
`x-previfoc-stale: true`.

## Reproducción

```sh
pnpm typecheck
WRANGLER_LOG_PATH=/tmp/release001-final-test.log pnpm test
WRANGLER_LOG_PATH=/tmp/release001-final-dry.log pnpm deploy:dry-run
WRANGLER_LOG_PATH=/tmp/release001-deploy.log pnpm run deploy
```

Resultados finales: 50 pruebas Vitest/workerd, 6 pruebas Python, staging de
9.512 assets, upload lógico de 35,46 KiB (8,95 KiB gzip) y bundle de 36.309
bytes frente a la guarda de 1 MiB.

## Rollback y desactivación

No se ha ejecutado todavía el ensayo de rollback. El candidato anterior es
funcional y usa el mismo KV:

```sh
pnpm exec wrangler rollback c9ff2a89-6e1d-4d7e-b91f-520e95496e2c \
  --name previfoc-osmand \
  --message "RELEASE-001 rollback controlado"
```

Un rollback de versión no elimina la clave `current`. Después debe comprobarse
`/health`, `/status.json` y una tesela antes de darlo por válido.

Para desactivar el cron de forma reproducible, establecer temporalmente
`"crons": []` en `wrangler.jsonc` y ejecutar `pnpm run deploy`. No basta con
comentar la propiedad. Restaurar `"crons": ["7 * * * *"]` y volver a desplegar
para reactivarlo.

## Pendiente para cerrar RELEASE-001

- observar al menos una invocación real del cron horario;
- completar Android/iOS con el `.osf` público y la capa como overlay;
- verificar expiración/repetición de petición en dispositivo;
- ensayar fallo de fuente y cambio de fecha a modo gris;
- ejecutar y revertir el rollback sin perder `current`;
- fechar y firmar la matriz final de aceptación.
