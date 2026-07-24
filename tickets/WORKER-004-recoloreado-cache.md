# WORKER-004 — Recolorear y cachear teselas en el Worker

**Estado:** completado  
**Dependencias:** [WORKER-003](./WORKER-003-estado-kv.md)  
**Siguiente:** [WEB-001](./WEB-001-pagina-informativa.md)

## Objetivo

Servir la ruta XYZ definitiva cambiando la paleta de las plantillas según el estado actual, con comportamiento seguro para datos obsoletos y caché coherente.

## Alcance

- Validar `/tiles/{z}/{x}/{y}.png` para z6–14 y rangos XYZ.
- Obtener la plantilla correspondiente mediante `ASSETS`.
- Devolver la tesela transparente con 200 si no existe una plantilla para una coordenada válida.
- Localizar `PLTE`, sustituir RGB de índices 1–7 y recalcular su CRC.
- Mantener `IDAT`, alpha y borde sin cambios.
- Aplicar nivel 1 `#A4CC87`, nivel 2 `#FF9700` y nivel 3 `#E83D35`.
- Aplicar `#808080` a todas las zonas cuando falte estado o sea obsoleto.
- Cachear mediante una clave interna que incluya `snapshotId` o `stale:{fecha-local}`.
- Publicar cabeceras de contenido, caché, ETag, snapshot y obsolescencia.

## Respuesta esperada

- `Content-Type: image/png`.
- `Cache-Control: public, max-age=3600`.
- `ETag` derivado de snapshot y coordenada.
- `X-Previfoc-Snapshot` cuando exista.
- `X-Previfoc-Stale: true|false`.

## Fuera de alcance

- Decodificar o recomprimir PNG.
- Cloudflare Images.
- Purga global de caché.
- Render bajo demanda desde GeoJSON.

## Entregables

- Handler XYZ.
- Mutador PNG/CRC compatible con Workers.
- Integración con Cache API.
- Pruebas de rutas y fixtures visuales.

## Criterios de aceptación

- [x] Una tesela mixta muestra cada zona con su nivel correspondiente.
- [x] Nivel 3 usa exactamente el rojo acordado.
- [x] El fondo y el mapa base permanecen visibles.
- [x] Estado ausente u obsoleto produce gris, nunca colores del día anterior.
- [x] `IDAT` es idéntico al de la plantilla.
- [x] Cambiar snapshot cambia inmediatamente la clave interna de caché.
- [x] El cambio de día invalida visualmente el color aunque no haya ejecutado el cron.
- [x] Coordenadas inválidas no provocan acceso arbitrario a assets.
- [x] La respuesta recoloreada se decodifica como PNG válido.

## Cierre de sesión

Este ticket aprueba la barrera C. Registrar latencia en frío/caliente y confirmar que no se requieren R2 ni Images.

## Cierre de WORKER-004 — 2026-07-18

La ruta `/tiles/{z}/{x}/{y}.png` sirve ya la representación dinámica definitiva.
Valida de forma estricta z6–14 y los rangos `0 <= x,y < 2^z` antes de leer KV,
caché o assets. Para una XYZ cubierta solicita a `ASSETS` una ruta canónica
reconstruida a partir de tres enteros; una respuesta 404 utiliza el
`transparent.png` congelado y conserva exactamente sus bytes. `GET` y `HEAD`
están admitidos; el resto recibe 405 con `Allow: GET, HEAD`. Se añadió también
revalidación condicional mediante `If-None-Match`/304.

### Mutación PNG y contrato visual

`src/png.ts` contiene un mutador sin dependencias de Node, decodificadores ni
recompresión. Recorre los chunks con lecturas big-endian y valida firma,
límites, CRC de entrada, `PLTE` único de 27 bytes e `IEND` final. Sustituye solo
los 21 bytes RGB de `PLTE[1:8]` y los cuatro bytes del CRC de ese chunk. El
resto del archivo, incluidos `IHDR`, `tRNS`, `IDAT`, borde e índices, permanece
byte a byte idéntico. El CRC-32 se implementa con el polinomio PNG/IEEE
`0xEDB88320` y solo APIs disponibles en Workers.

La correspondencia final es:

| Nivel/estado | RGB |
|---|---|
| 1 | `#A4CC87` |
| 2 | `#FF9700` |
| 3 | `#E83D35` |
| ausente, inválido u obsoleto | `#808080` en las siete zonas |

Se conservaron dos controles visuales de la tesela real z6/31/24:

- `data/worker-004/mixed-levels-z6-31-24.png`: niveles
  `[1,1,1,2,2,3,3]`, SHA-256
  `d805939c234a84635bf70d553b854bfbec54ce8a7352ca82b3430dc866504ad1`;
- `data/worker-004/stale-gray-z6-31-24.png`: siete zonas grises, SHA-256
  `6be7a900cdbfc45ce3f5eb8367bab5c60d9b336b601a31bb452db596c766b249`.

Ambos son PNG indexados 256x256 válidos con los cinco chunks congelados. Su
`IDAT` compartido conserva SHA-256
`c943ffb1fb0d11b570bc85291ecb13c7b5db304e03f32a7c39c2cb85ca187414`.
El decodificador de referencia y Pillow producen fondo RGBA `(0,0,0,0)`,
límites `(0,0,0,179)`, rellenos con alpha 77 y exactamente los RGB anteriores.
La inspección directa confirma transparencia, costa y límites intactos, sin
colores residuales en el control gris.

### Estado, cabeceras y caché

Cada petición resuelve primero `current` mediante el repositorio validado de
WORKER-003 y recalcula obsolescencia contra la fecha civil actual de Madrid.
Una ausencia, JSON/esquema/hash inválido o fecha fuente anterior no propaga el
último color: todos esos casos convergen en la misma representación gris
segura.

La clave privada de Cache API tiene versión y forma lógica:

```text
https://previfoc-tile-cache.invalid/v1/{tag}/{z}/{x}/{y}.png
tag = snapshotId                 si el estado es actual
tag = stale:{YYYY-MM-DD-Madrid}  en cualquier modo seguro gris
```

Por ello un snapshot nuevo no puede acertar en una entrada anterior. Al llegar
la medianoche local, incluida la transición CEST comprobada a las 22:00 UTC,
la misma tesela cambia de namespace a `stale:{nueva-fecha}` aunque el cron no
haya corrido. Las entradas grises comparten bytes dentro de un mismo día, pero
`X-Previfoc-Snapshot` se compone después del acierto de caché para reflejar
siempre el estado leído en esa petición y no una cabecera antigua almacenada.

Las respuestas 200 publican exactamente `Content-Type: image/png`,
`Cache-Control: public, max-age=3600`, un ETag de representación y coordenada,
`X-Previfoc-Stale: true|false` y `X-Previfoc-Snapshot` cuando existe estado
validado. La escritura en Cache API se delega con `waitUntil`; un fallo de
caché no impide generar la tesela desde Static Assets.

### Pruebas y barrera C

La suite nueva prueba paletas mixta/gris, rojo exacto, CRC, corrupción, `IDAT`
inmutable, estado ausente/inválido/obsoleto, fallback transparente, cabeceras,
GET/HEAD/304, acierto caliente, cambio de snapshot, medianoche CEST y rutas
fuera de rango o manipuladas. El resultado del Worker se compara por SHA-256
con los controles generados por el recoloreador independiente.

Comandos de cierre:

```sh
pnpm typecheck
WRANGLER_LOG_PATH=/tmp/worker004-wrangler-test.log pnpm test
.venv-geo/bin/python -m unittest discover -s tests -v
pnpm check:assets
WRANGLER_LOG_PATH=/tmp/worker004-wrangler-dry-run.log pnpm deploy:dry-run
```

Resultados: typecheck correcto; **5 ficheros y 48 pruebas** Vitest/workerd
correctas; **52 pruebas** Python heredadas correctas; staging verificado con
9.509 assets, 9.507 teselas cubiertas y 4.603.224 bytes de teselas; dry run con
`Total Upload: 34.42 KiB / gzip: 8.75 KiB`, bundle de 35.248 bytes frente a la
guarda de 1 MiB. La primera ejecución de cada suite que abre sockets locales
quedó bloqueada por el sandbox; repetida con permiso fuera de él, pasó completa.

Un microbenchmark local sobre el bundle compilado, Node 24.6.0,
Static Asset y caché en memoria, sin red ni latencia KV, midió 250 peticiones
frías y 1.000 calientes. La ruta fría (lectura de plantilla, validación de CRC,
recoloreado y `put`) obtuvo mediana **0,075 ms** y p95 **0,262 ms**; la caliente
(lectura de estado y `match`) mediana **0,029 ms** y p95 **0,046 ms**. Son
medidas del coste del código, no una predicción de latencia de red de Cloudflare;
la latencia de borde se medirá en RELEASE-001 cuando exista despliegue público.

No se requieren R2 ni Cloudflare Images: las 9.507 plantillas caben holgadamente
en Static Assets, el Worker solo cambia 21 bytes y un CRC, y Cache API cubre las
representaciones derivadas sin persistencia adicional ni purga global. No se
añadieron bindings, namespaces ni infraestructura, no se desplegó y no se
inició WEB-001. Con recoloreado, obsolescencia y caché demostrados, queda
aprobada la barrera C.
