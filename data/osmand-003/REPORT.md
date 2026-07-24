# OSMAND-003 — Informe del paquete `.osf`

Fecha de construcción: 2026-07-18. Estado: artefacto y validación automática
terminados; Worker final operativo; importación acreditada en iOS y pendiente
en Android; visualización física contra el Worker todavía pendiente.

## Artefacto congelado

- ruta versionada: `static/previfoc.osf`;
- versión de artefacto: `1.0.0`;
- versión de plugin OsmAnd: `1`;
- SHA-256: `dab5d3cf27671088bd506f7680366bb75b9db3b3f3df0d4dca34f01d2ff85ec7`;
- tamaño: 1.792 bytes;
- `items.json`: SHA-256
  `ba0a5d151548163d4f51defd671ff689d2ed7277266dc894452a485a4e85eb48`;
- `res/previfoc.png`: PNG RGBA 256 × 256, SHA-256
  `bce23d3f4a321c93bbb6ebb5ba62028ef380d63eccfc82637f06f1df5bd71cfd`.

El ZIP contiene exactamente `items.json` y `res/previfoc.png`. No contiene
teselas, SQLite, estado diario, historial, credenciales ni código ejecutable.
Las marcas de tiempo, permisos, orden, JSON, icono y compresión son
deterministas; dos construcciones producen los mismos bytes.

## Contrato instalado

- plugin: `com.davidramosweb.previfoc`, versión `1`;
- fuente: `PREVIFOC (no oficial)`;
- tipo: `MAP_SOURCES`, remoto, no SQLite;
- URL XYZ:
  `https://previfoc.davidramosweb.com/tiles/{0}/{1}/{2}.png`;
- Web Mercator esférico, Y no invertida, z6–14;
- PNG de 256 px, extensión `.png`, densidad de bit declarada `8`;
- `timesupported: true`, `expire: 60` (minutos);
- descripción en español e inglés con aviso no oficial, regla preventiva,
  atribución, limitaciones, instalación y enlace a 112CV.

El hostname final se reserva como origen estable del Worker. OSMAND-003 no ha
modificado DNS ni desplegado; RELEASE-001 debe asociar el Worker a ese hostname
antes de considerar operativo el artefacto.

## Referencias reales del formato

Se descargó y abrió el paquete de ejemplo oficial publicado por OsmAnd en
`https://osmand.net/uploads/plugins/model.plugin/1/model.plugin-1.osf`. El
snapshot observado mide 85.604 bytes y tiene SHA-256
`e6df59a1aa31caf5bfb7b21d0bdbc94f71259e20ae29eea30711515bca1a73e1`.
Confirma el ZIP con `items.json`, `PLUGIN`, `RESOURCES`, referencias de icono
con `@nombre.png` y recursos bajo `res/`.

Además se revisó el código fuente oficial exacto de las dos aplicaciones:

- Android, commit `9d7a6a64919c0b7182324740acd378c720d7e94a`: el exportador
  `MapSourcesSettingsItem` escribe `MAP_SOURCES`; al importar convierte
  `expire` menor de 3.600.000 de minutos a milisegundos y aplica la caducidad
  solo cuando `timesupported` es verdadero;
- iOS, commit `2cb47843bc9b538ff0026d2b072a410fdca3fc93`: el exportador
  `OAMapSourcesSettingsItem` conserva los mismos campos y `OATileSource`
  convierte `expire * 60000` al instalar la fuente.

Por tanto, `expire: 60` expresa una hora en ambas implementaciones. La fuente
temporal sí fue utilizada en OsmAnd iOS 5.3.3 durante OSMAND-002, pero no se
presenta esa evidencia como exportación o importación del paquete final.

Documentación oficial contrastada:

- `https://osmand.net/docs/user/plugins/custom/`;
- `https://osmand.net/docs/user/map/raster-maps/`;
- `https://osmand.net/docs/user/personal/import-export/`.

## Validador y barreras de publicación

`tools/osmand_package.py` carga el contrato de
`config/osmand_package.json`, construye el ZIP y valida:

- extensión, tamaño, CRC, cifrado, duplicados, symlinks y rutas inseguras;
- lista exacta de miembros, sin datos offline;
- igualdad byte a byte de `items.json` y del icono reproducible;
- plugin, recurso, fuente única, URL HTTPS, XYZ, zoom y caducidad;
- enlaces de ayuda, atribución y limitaciones bajo el origen público.

El staging, los tests y el dry run invocan `check:osf`, así que no pueden
publicar silenciosamente un paquete que difiera del contrato. La suite Python
añade seis pruebas: artefacto real, reproducibilidad, inventario mínimo,
origen inseguro, manipulación de JSON y miembro extra/traversal.

Cloudflare asigna por defecto a la extensión `.osf` el MIME musical
`application/vnd.yamaha.openscoreformat`. Para evitar esa asociación errónea,
`/previfoc.osf` pasa por el Worker y se entrega como
`application/octet-stream`, con `Content-Disposition: attachment;
filename="previfoc.osf"` y `X-Content-Type-Options: nosniff`, sin alterar el
cuerpo. Una prueba workerd congela el SHA-256 de la respuesta.

Comandos:

```sh
pnpm build:osf
pnpm check:osf
pnpm test:osf
pnpm check:assets
```

## Validación física pendiente

No había Android o iPhone conectado/controlable en esta sesión. Quedan sin
acreditar para el paquete final: importación desde cero, activación como
overlay, lectura de 60 minutos en la UI, acceso a la descripción, reinstalación
sin duplicado y las capturas de importación/activación en ambas plataformas.
El procedimiento y la matriz de evidencia están en `data/osmand-003/INSTALL.md`.

No debe marcarse OSMAND-003 como completado hasta recibir esa evidencia o una
aceptación explícita de las limitaciones. La prueba de dibujo requiere ejecutar
el despliegue controlado previsto en RELEASE-001, porque el `.osf` apunta
deliberadamente al hostname final.

## Evidencia iOS recibida

El usuario confirmó `https://previfoc.davidramosweb.com` como hostname
definitivo y probó la importación del artefacto final en un iPhone físico. Los
originales recibidos se conservaron byte a byte:

| Archivo | Dimensiones | SHA-256 | Qué acredita |
|---|---:|---|---|
| `evidence/ios-import-2026-07-18.jpg` | 588 × 1280 | `9ed5dcc30751f6423dd5f24e8c0213e360383185d5293df215c07c4dd89e0cb3` | OsmAnd reconoce e importa el plugin; presenta nombre, aviso y enlaces. |
| `evidence/ios-source-selected-as-base-2026-07-18.jpg` | 588 × 1280 | `26012cfe583b0578d0114cbbbbfbcf97a23d05b8c587a588d2847fb7be2b2b36` | La fuente aparece registrada y seleccionable. |

La segunda captura pertenece a **Capa base**, según su propio encabezado y el
control “Transparencia del mapa base”. Por ello no demuestra todavía el uso
como overlay. Tampoco puede mostrar teselas: el hostname definitivo aún no
está asociado al Worker. Tras desplegar hay que repetir la selección desde
Superposición/Overlay, comprobar el dibujo y obtener la ficha con URL, z6–14 y
60 minutos.

## Worker final

El 2026-07-18, con autorización explícita del usuario, se desplegó la versión
`578e178b-7544-41a9-9475-cd063929f08c` en
`https://previfoc.davidramosweb.com` y
`https://previfoc-osmand.quiet-mountain-f8dd.workers.dev`. El dominio
personalizado tiene HTTPS válido y el cron definitivo continúa siendo
`7 * * * *` UTC.

La primera captura validada se publicó con snapshot
`sha256:2542366c8bfa830253174262d41d7855d64f36a2e85cdc47e7ccde45fa308588`.
La fuente marcaba `2026-07-18 17:05:48.0`; las zonas 53–59 quedaron en niveles
`2, 2, 2, 3, 2, 3, 2`. `/health` y `/status.json` responden 200 y el estado se
presenta como actual. La tesela `6/31/24.png` responde 200 con
`x-previfoc-stale: false`, el snapshot correcto y SHA-256
`d82b132f57297ca0607508a1b4e062ff0fd497f9199eef143b94049a174556f9`.

El instalador público responde 200, 1.792 bytes, MIME
`application/octet-stream`, nombre de descarga `previfoc.osf` y el mismo
SHA-256 congelado del artefacto local. Ya no existe un bloqueo de red para la
prueba física.
