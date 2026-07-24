# TILES-001 — Diseñar y probar el formato de tesela plantilla

**Estado:** completado  
**Dependencias:** [GEO-004](./GEO-004-comparacion-visual.md)  
**Siguiente:** [TILES-002](./TILES-002-generar-piramide-xyz.md)

## Objetivo

Definir un PNG indexado que permita cambiar los colores de las siete zonas modificando únicamente su paleta, sin decodificar ni volver a renderizar la imagen en Cloudflare.

## Contexto

La geometría es fija y solo cambia el nivel de cada zona. El PNG debe conservar índices estables para que un Worker pueda sustituir entradas `PLTE` y recalcular el CRC.

## Contrato de paleta

| Índice | Uso |
|---:|---|
| 0 | fondo totalmente transparente |
| 1 | zona 53 / `1N` |
| 2 | zona 54 / `1S` |
| 3 | zona 55 / `2` |
| 4 | zona 56 / `3` |
| 5 | zona 57 / `4` |
| 6 | zona 58 / `5` |
| 7 | zona 59 / `6` |
| 8 | límites negros |

Los índices 1–7 tendrán alpha fijo del 30 % y el borde alpha del 70 %. Los RGB de 1–7 son marcadores reemplazables; el color final lo decide el nivel.

## Alcance

- Implementar la codificación PNG indexada con `PLTE` y `tRNS` deterministas.
- Rasterizar una tesela pequeña que contenga al menos dos zonas y un límite.
- Implementar una utilidad de prueba que sustituya las siete entradas de color y recalcule CRC.
- Decodificar el resultado con una biblioteca independiente para validar integridad y píxeles.
- Evaluar visualmente bordes sin antialias como simplificación aceptada para el MVP.

## Fuera de alcance

- Pirámide completa.
- Caché o Worker.
- Etiquetas, iconos, patrones y antialias.

## Entregables

- Especificación de paleta consolidada.
- Codificador de plantilla y recoloreador de referencia.
- Fixtures PNG original, recoloreado y transparente.
- Pruebas unitarias de chunks y CRC.

## Criterios de aceptación

- [x] Los índices 0–8 mantienen siempre el mismo significado.
- [x] El fondo es transparente y permite ver un mapa base.
- [x] Una tesela con varias zonas admite colores distintos simultáneamente.
- [x] El borde continúa negro después del recoloreado.
- [x] El PNG recoloreado se abre en al menos dos decodificadores independientes.
- [x] Modificar la paleta no altera `IDAT`.
- [x] El resultado es visualmente aceptable a 256×256 y no muestra halos blancos.

## Cierre de sesión

Congelar la versión del formato. Cualquier cambio posterior obliga a regenerar toda la pirámide de TILES-002.

## Cierre de TILES-001 — 2026-07-18

El formato queda congelado como `previfoc-indexed-template-v1`. TILES-002 deberá
producir archivos conformes a esta versión; cualquier cambio en significado de
índices, estructura, `PLTE`, `tRNS` o alpha requiere una nueva versión y la
regeneración completa de su futura pirámide. TILES-002 no se ha iniciado.

### Entrada inmutable comprobada

Antes de implementar se ejecutaron correctamente:

```sh
.venv-geo/bin/python tools/geo_sources.py validate
.venv-geo/bin/python tools/geo_crosswalk.py validate
.venv-geo/bin/python tools/geo_zones.py validate
.venv-geo/bin/python tools/geo_compare.py validate
```

TILES-001 consume, sin regenerar ni modificar GEO-002/003/004,
`geometry_version = sha256:e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0`.
Se comprobaron directamente los hashes congelados:

- `zones.gpkg`: `e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0`;
- `zones.geojson`: `b76ffaeec4eb9c75ee23991ed9386136d74d94a5bc2603700d65b37e6fb528c2`;
- `crosswalk.csv`: `0ca0ed22ccaaa6994d4701bd75da1d1355fcb945f4e7dfaf1b22472743294876`.

### Especificación binaria congelada

- Firma PNG estándar; `IHDR` de 13 bytes: 256×256, profundidad 8, color tipo 3
  (indexado), compresión/filtro método 0 y sin entrelazado.
- Exactamente un chunk de cada tipo y en orden `IHDR`, `PLTE`, `tRNS`, `IDAT`,
  `IEND`; no se permiten chunks auxiliares.
- `PLTE`: 27 bytes, nueve tripletas. Índice 0 RGB negro invisible; índices 1–7
  marcadores `#112233`, `#223344`, `#334455`, `#445566`, `#556677`, `#667788`,
  `#778899`; índice 8 negro. Los marcadores no son colores finales.
- Conversión alpha: `floor(fracción × 255 + 0.5)`. Fondo 0 % → 0 (`0x00`),
  zonas 30 % → 77 (`0x4D`, 30,196078… % efectivo) y borde 70 % → 179
  (`0xB3`, 70,196078… % efectivo).
- `tRNS`: nueve bytes exactos `00 4d 4d 4d 4d 4d 4d 4d b3`.
- Cada CRC-32 se calcula sobre `tipo || datos`. El recoloreador solo sustituye
  los 21 bytes de `PLTE[1:8]` y cambia su CRC; `IDAT` debe quedar byte a byte
  idéntico.

### Implementación, fixtures y resultado

`tools/tile_template.py` implementa codificación, análisis estricto, CRC,
decodificador indexed-8 independiente, recoloreado de referencia, inspección,
construcción y validación reproducible. El fixture sintético de 256×256 contiene
dos zonas rectangulares (índices 1 y 2), contorno, un límite común negro de tres
píxeles y fondo índice 0. Solo se rasterizó este caso, con bordes duros y sin
antialias.

- `fixture-original.png`: 373 bytes; SHA-256
  `85928c0702227ddfa4e8e650e7b3851dd65387106ad0f777751739661c7b469b`;
- `fixture-recolored.png`: 373 bytes; SHA-256
  `6c1be4dc6cd7c9d919996f97872946dc32bfb98c0f63dae6e663e2f8de4fe4f7`;
- `fixture-transparent.png`: 201 bytes; SHA-256
  `00af44e300322d960f89aaa5dac93b0517fd1625ec0c058f3212661276a0d0ba`.

Original y recoloreado comparten un `IDAT` de 256 bytes, SHA-256
`24a86659535403a74fa71bb750c8c3dd6e342a229233ef266586ab055f52d3c0`.
Solo difieren los 21 bytes de colores de zona y el CRC de `PLTE`. Pillow 11.3.0
y el decodificador independiente basado en `zlib` y filtros PNG producen los
mismos índices y RGBA. Se verificaron fondo con alpha cero, dos colores de zona
simultáneos, borde negro con alpha 179, ausencia de cualquier píxel blanco/halo
y fixture transparente completamente invisible.

### Reproducibilidad y pruebas

```sh
.venv-geo/bin/python tools/tile_template.py build
.venv-geo/bin/python tools/tile_template.py validate
.venv-geo/bin/python -m unittest tests.test_tile_template -v
.venv-geo/bin/python -m unittest discover -s tests -v
```

Las 10 pruebas específicas cubren firma, chunks, longitudes, orden, CRC, IHDR,
contrato de índices, `PLTE`, `tRNS`, `IDAT` inmutable, recoloreado de las siete
entradas, dos decodificadores, transparencia, colores simultáneos, borde, halos,
rechazo de corrupción y repetición byte a byte. La especificación ampliada,
limitaciones, hashes y versiones están en `data/tiles-001/REPORT.md` y
`data/tiles-001/manifest.json`.

La suite completa pasa 37 pruebas. Su primer intento dentro del sandbox quedó
limitado exclusivamente porque las seis pruebas heredadas de GEO-001 no podían
abrir un servidor HTTP en `127.0.0.1`; repetida fuera de esa restricción, pasa
37/37. La inspección visual directa de los tres fixtures confirma rellenos
simultáneos, límite negro persistente, bordes duros limpios, ausencia de halos y
transparencia del fondo coherente con las comprobaciones RGBA.

### Límites conservados

No se generó pirámide XYZ, no se creó TILES-002 y no se implementó Worker,
caché o Cloudflare. Tampoco se añadieron etiquetas, iconos, patrones,
antialias ni colores finales de producto. La geometría congelada no cambió.
