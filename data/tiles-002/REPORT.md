# TILES-002 — Pirámide XYZ estática

**Formato:** `previfoc-indexed-template-v2`  
**Geometría:** `sha256:e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0`  
**CRS canónico:** `EPSG:25830` (sin modificar)  
**CRS de render:** `EPSG:3857` (solo en memoria)

## Resultado

| Zoom | Teselas | Bytes PNG |
|---:|---:|---:|
| 6 | 2 | 2098 |
| 7 | 4 | 4547 |
| 8 | 8 | 9611 |
| 9 | 19 | 23443 |
| 10 | 50 | 56477 |
| 11 | 151 | 146912 |
| 12 | 501 | 417144 |
| 13 | 1838 | 1323703 |
| 14 | 6934 | 4572407 |

Teselas con cobertura: **9507**. Tesela transparente compartida: **1**. Assets totales del entregable: **9515**, por debajo del límite de 19000. Los PNG de despliegue ocupan **6556571 bytes**; el total exacto del entregable se registra en `manifest.json`.

## Algoritmo XYZ y rasterizado

La capa `zones` se abre en modo solo lectura y se exige `MULTIPOLYGON EPSG:25830`. Sus siete geometrías se reproyectan a EPSG:3857 exclusivamente en memoria. Para cada z6–z14 se calcula el rango candidato desde la envolvente y se conserva una tesela solo si un polígono exacto la intersecta. La ruta es `{z}/{x}/{y}.png`; Y aumenta hacia el sur (XYZ, nunca TMS).

Los rellenos se dibujan con índices 1–7 y una banda diagonal global de 2 px cada 12 px usa 8–14. Todos los anillos originales se trazan después con índice 15, negro, ancho fijo de 2 px y bordes duros. El patrón se alinea en coordenadas de píxel globales para no crear discontinuidades entre teselas. `tools/tile_template.py` codifica cada matriz con el contrato binario congelado y vuelve a decodificar muestras.

## Estrategia anti-seams

Todas las coordenadas se convierten a una única rejilla global de píxeles Web Mercator. Cada ventana se rasteriza con 8 px de overscan y se recorta al centro exacto; el recorte geométrico queda fuera de la tesela publicada. Se compararon teselas individuales contra los recortes de un render compartido de dos teselas en cada dirección adyacente existente. Las 17 parejas fueron idénticas byte a byte; z6 no tiene pareja vertical cubierta y se registra sin inventar un asset fuera de cobertura.

## Verificación visual y automática

Los mosaicos `controls/z6-overview.png`, `z10-overview.png` y `z14-overview.png` se montan desde las teselas XYZ reales, con Y creciente hacia abajo y un marco transparente. `controls/z14-seam-detail.png` conserva dos teselas contiguas a resolución nativa. Se revisan costa, límites internos, trama, cuatro esquinas, continuidad, orientación norte-sur, transparencia exterior y ausencia de blanco visible. Tres muestras de cada zoom se decodifican con el validador TILES-001; los índices observados son 0–15 y los alpha siguen siendo 0/77/179.

## Reproducibilidad

```sh
.venv-geo/bin/python tools/tile_pyramid.py build
.venv-geo/bin/python tools/tile_pyramid.py validate
.venv-geo/bin/python -m unittest tests.test_tile_pyramid -v
.venv-geo/bin/python -m unittest discover -s tests -v
```

`build` y `validate` ejecutan primero las cinco barreras GEO-001→TILES-001. `validate` regenera la pirámide completa en un directorio temporal y exige el mismo conjunto de rutas y bytes. `tiles.sha256` fija cada ruta de tesela y su SHA-256; su propio hash actúa como huella compacta de la pirámide.

## Limitaciones

El borde y la trama no usan antialias y su grosor cartográfico varía con el zoom. Los RGB 1–14 son marcadores reemplazables, no el estilo final. No se sirve HTTP ni se genera TMS/MBTiles.
