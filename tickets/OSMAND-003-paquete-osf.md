# OSMAND-003 — Generar y validar el paquete `.osf`

**Estado:** en validación física  
**Dependencias:** [WEB-001](./WEB-001-pagina-informativa.md)  
**Siguiente:** [RELEASE-001](./RELEASE-001-despliegue-aceptacion.md)

## Objetivo

Crear el instalador definitivo de la fuente XYZ y comprobar que la misma configuración funciona en OsmAnd Android e iOS.

## Contexto

El `.osf` contiene configuración estable, no el estado diario. Las teselas se actualizan desde la URL remota cada hora.

## Alcance

- Crear/exportar una fuente real desde OsmAnd y usarla como referencia del formato.
- Empaquetar `MAP_SOURCES`, nombre, icono, URL XYZ, z6–14 y expiración de 60 minutos.
- Incluir atribución, enlace a la página, limitaciones y aviso no oficial.
- Validar estructura ZIP e `items.json` antes de publicar.
- Instalar el artefacto final en Android e iOS desde cero.
- Documentar pasos y diferencias de interfaz.

## Fuera de alcance

- Incrustar teselas o estado actual.
- Actualización automática del propio `.osf`.
- Paquete SQLite offline.

## Entregables

- `previfoc.osf` versionado.
- Validador automatizado del paquete.
- Guía de instalación Android/iOS.
- Capturas de instalación y activación.

## Criterios de aceptación

- [ ] El paquete se importa sin editar archivos en Android.
- [x] El paquete se importa sin editar archivos en iOS.
- [ ] La fuente queda configurada como overlay XYZ z6–14.
- [ ] La expiración objetivo es 60 minutos en ambas plataformas.
- [x] La URL apunta al Worker definitivo.
- [x] La descripción enlaza avisos, atribución e instalación.
- [ ] Reinstalar el paquete no introduce fuentes duplicadas inesperadas.

## Cierre de sesión

Congelar hash y versión del `.osf`. RELEASE-001 usará exactamente el artefacto validado.

## Avance verificable de OSMAND-003 — 2026-07-18

La implementación, el artefacto versionado y toda la validación automatizable
están terminados. El ticket permanece abierto porque no había un Android o
iPhone conectado/controlable para importar el paquete final desde cero y
capturar las pantallas requeridas.

### Paquete congelado

`static/previfoc.osf` versión `1.0.0` es un ZIP reproducible de 1.792 bytes con
SHA-256
`dab5d3cf27671088bd506f7680366bb75b9db3b3f3df0d4dca34f01d2ff85ec7`.
Contiene exclusivamente:

- `items.json`, SHA-256
  `ba0a5d151548163d4f51defd671ff689d2ed7277266dc894452a485a4e85eb48`;
- `res/previfoc.png`, PNG RGBA 256 × 256, SHA-256
  `bce23d3f4a321c93bbb6ebb5ba62028ef380d63eccfc82637f06f1df5bd71cfd`.

No incluye teselas, SQLite ni estado diario. Instala un `PLUGIN`, sus
`RESOURCES` y una única `MAP_SOURCES` remota con identificador estable
`com.davidramosweb.previfoc`, nombre `PREVIFOC (no oficial)`, Web Mercator XYZ
sin Y invertida, PNG 256 px, z6–14 y `timesupported: true` con `expire: 60`.

La URL congelada es
`https://previfoc.davidramosweb.com/tiles/{0}/{1}/{2}.png`. Los enlaces de la
descripción usan el mismo origen para instalación, atribución y limitaciones,
y enlazan además la fuente oficial 112CV. El hostname se eligió como origen
estable del Worker; no se modificó DNS ni se desplegó. RELEASE-001 tendrá que
asociar el Worker a ese hostname antes de que la URL sea operativa.

### Referencia y compatibilidad del formato

Se inspeccionó un `.osf` real publicado por OsmAnd, el ejemplo oficial
`model.plugin-1.osf`, SHA-256
`e6df59a1aa31caf5bfb7b21d0bdbc94f71259e20ae29eea30711515bca1a73e1`,
y el código fuente actual de ambos importadores/exportadores:

- Android commit `9d7a6a64919c0b7182324740acd378c720d7e94a`;
- iOS commit `2cb47843bc9b538ff0026d2b072a410fdca3fc93`.

Android convierte un `expire` pequeño de minutos a milisegundos e iOS instala
`expire * 60000`; ambos interpretan `60` como una hora. La estructura reproduce
los campos exportados `MAP_SOURCES` comunes a ambas implementaciones. La
evidencia de OSMAND-002 acredita una fuente temporal real en iOS 5.3.3, no la
importación del paquete final, y se mantiene diferenciada.

### Generador, validador y publicación segura

`tools/osmand_package.py` y `config/osmand_package.json` construyen y validan el
artefacto sin dependencias gráficas. El validador exige configuración exacta,
HTTPS, plantilla XYZ, zoom, caducidad, inventario ZIP mínimo, CRC, rutas
normalizadas, ausencia de duplicados/cifrado/symlinks y recursos reproducibles
byte a byte. Se añadieron seis pruebas Python de aceptación y manipulación.

Cloudflare identifica por defecto `.osf` como el formato musical Yamaha. Para
evitarlo, `/previfoc.osf` pasa por el Worker, que entrega los mismos bytes como
`application/octet-stream`, fuerza el nombre de descarga y añade `nosniff`.
Una prueba workerd congela el SHA-256 servido.

La página ya presenta el paquete como versión 1.0.0 y explica el reemplazo al
reinstalar. La guía completa de Android/iOS, diferencias de interfaz, caché,
reinstalación, limitaciones y captura de evidencia está en
`data/osmand-003/INSTALL.md`; el informe auditable está en
`data/osmand-003/REPORT.md`.

### Verificación ejecutada

```sh
pnpm typecheck
WRANGLER_LOG_PATH=/tmp/osmand003-vitest-final.log pnpm test
pnpm check:assets
WRANGLER_LOG_PATH=/tmp/osmand003-dry-run-final.log pnpm deploy:dry-run
```

Resultados: typecheck correcto; 5 ficheros y 50 pruebas Vitest/workerd
correctas; 6 pruebas Python correctas; staging íntegro de 9.513 assets; dry run
correcto con `Total Upload: 35.46 KiB / gzip: 8.95 KiB` y bundle de 36.309
bytes frente a la guarda de 1 MiB.

### Barrera pendiente

Siguen abiertas cuatro casillas de aceptación porque requieren, además de
la configuración ya comprobada, el Worker accesible y evidencia física del
paquete final en Android e iOS: importación desde cero, selección como overlay,
caducidad visible, enlaces, reinstalación y capturas. La visualización contra
la URL final exige adelantar el despliegue controlado previsto en RELEASE-001;
el ticket no se marca como completado hasta obtener la evidencia restante o
una aceptación explícita de las limitaciones.

### Evidencia iOS recibida — 2026-07-18

El usuario confirmó el hostname definitivo
`https://previfoc.davidramosweb.com` e importó el `.osf` final en un iPhone
físico. Se archivaron sin transformación dos JPEG de 588 × 1280 px:

- `data/osmand-003/evidence/ios-import-2026-07-18.jpg`, SHA-256
  `9ed5dcc30751f6423dd5f24e8c0213e360383185d5293df215c07c4dd89e0cb3`;
- `data/osmand-003/evidence/ios-source-selected-as-base-2026-07-18.jpg`,
  SHA-256
  `26012cfe583b0578d0114cbbbbfbcf97a23d05b8c587a588d2847fb7be2b2b36`.

La primera acredita que OsmAnd reconoce el plugin, muestra el nombre, el aviso
no oficial, la regla preventiva y los cuatro enlaces, y permite aceptarlo sin
editar archivos. La segunda acredita que la fuente queda registrada y puede
seleccionarse, pero la pantalla se titula **Capa base** y muestra
“Transparencia del mapa base”; no acredita todavía la activación como
superposición. La ausencia de dibujo es esperable: el hostname confirmado aún
no sirve el Worker.

Para completar la prueba iOS, después del despliegue hay que seleccionar la
fuente desde **Superposición/Overlay**, no como capa base, y capturar el mapa y
la ficha de la fuente con URL/zoom/caducidad. Continúan pendientes Android, la
reinstalación y una exportación real de `MAP_SOURCES` desde el dispositivo.

### Worker final operativo — 2026-07-18

Con autorización explícita del usuario se creó el KV, se vinculó el dominio y
se desplegó el Worker definitivo. La versión activa es
`578e178b-7544-41a9-9475-cd063929f08c` y responde en:

- `https://previfoc.davidramosweb.com`;
- `https://previfoc-osmand.quiet-mountain-f8dd.workers.dev`.

El cron conserva `7 * * * *`. La primera captura se generó una sola vez con
`ingestCurrentStateCandidate`, `calculateSnapshotId` y
`validatePersistedCurrentState`, y se escribió en el KV de producción; no se
añadió un endpoint administrativo ni se alteró temporalmente el cron. El
snapshot actual es
`sha256:2542366c8bfa830253174262d41d7855d64f36a2e85cdc47e7ccde45fa308588`,
fecha fuente 2026-07-18, con niveles `53:2, 54:2, 55:2, 56:3, 57:2, 58:3,
59:2`.

La matriz HTTPS final devuelve 200 en raíz, `/health`, `/status.json`,
`/previfoc.osf` y la tesela `6/31/24.png`. Salud informa `current`, el estado
no es obsoleto, la tesela lleva `x-previfoc-stale: false` y el snapshot
correcto. El `.osf` descargado conserva SHA-256
`dab5d3cf27671088bd506f7680366bb75b9db3b3f3df0d4dca34f01d2ff85ec7`.
Ya puede repetirse la prueba de dibujo en OsmAnd.
