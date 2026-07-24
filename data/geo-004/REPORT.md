# GEO-004 — Comparación visual con el mapa oficial PREVIFOC

**Estado:** aprobado por revisión humana explícita.

La comparación no georreferencia ni digitaliza el PNG oficial. Renderiza exactamente las siete `MultiPolygon` congeladas por GEO-003 y usa únicamente escala uniforme, traslación e inversión del eje Y para compartir encuadre. No se ha simplificado, eliminado ninguna parte, rellenado ningún hueco ni modificado coordenadas.

## Referencia oficial fijada

- URL solicitada/final: `https://wpr.112cv.gva.es/external/api/storage/descargar/imagen/static/images/avisosmeteorologicos/zonasprevifoc.png`.
- Snapshot original intacto: `data/geo-004/snapshots/zonasprevifoc/df1c7c08765bcdae51a36d4efbd414911b975d75de878a04faf364cc8b905f7f.png`.
- Recuperación UTC: `2026-07-18T08:14:20Z`; Content-Type `image/png`; 500×835 px; 44982 bytes.
- SHA-256: `df1c7c08765bcdae51a36d4efbd414911b975d75de878a04faf364cc8b905f7f`.
- Licencia específica 112CV: `not_found`; el acceso público no se interpreta como licencia.
- Referencia prioritaria: `zonasprevifoc.png`. No se usaron buscadores, copias de terceros ni los JPEG secundarios.

## Entradas congeladas y barreras

- `zones.gpkg`: `e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0`; capa `zones`, EPSG:25830, siete `MULTIPOLYGON`.
- `zones.geojson`: `b76ffaeec4eb9c75ee23991ed9386136d74d94a5bc2603700d65b37e6fb528c2`; RFC 7946 EPSG:4326.
- `crosswalk.csv`: `0ca0ed22ccaaa6994d4701bd75da1d1355fcb945f4e7dfaf1b22472743294876`; 542 municipios.
- Antes de comparar se ejecutaron y exigieron `geo_sources.py validate`, `geo_crosswalk.py validate` y `geo_zones.py validate`.
- GEO-004 no modificó ni regeneró esos entregables.

## Registro visual

Transformación: `uniform_scale_translation_with_y_inversion`. Fórmulas: `x = scale * easting + translate_x`; `y = -scale * northing + translate_y`. Escala `0.002491290213226` px/m; traslaciones X `-1545.340970336761` px e Y `11266.542439887289` px. No hay deformación no lineal.

| Control | Coordenada EPSG:25830 | Pixel observado | Pixel proyectado | Residuo (px) |
|---|---|---|---|---:|
| `north_extreme` | `739206.005, 4519161.349` | `296.0, 8.0` | `296.236, 8.000` | 0.236 |
| `south_extreme` | `695675.387, 4190817.426` | `188.0, 826.0` | `187.788, 826.000` | 0.212 |
| `west_extreme` | `626576.389, 4368255.080` | `15.0, 384.0` | `15.643, 383.951` | 0.644 |
| `east_island_extreme` | `815520.530, 4422736.800` | `486.0, 248.0` | `486.357, 248.222` | 0.420 |

La superposición es técnicamente útil para orientación cualitativa porque los cuatro residuos son menores de 1,5 px. No se calcula ni presenta una diferencia píxel a píxel como métrica cartográfica.

Los colores, rellenos y el alfabeto de bloques de los renders son exclusivamente diagnósticos; no definen teselas ni estilo de producto.

## Controles revisados

Se conservaron 15 controles versionados y se comprobaron automáticamente 9 pares municipales que comparten frontera.

| ID | Zona esperada | Municipio o rasgo | Resultado | Limitación principal |
|---|---|---|---|---|
| `C01` | `3` | Rincón de Ademuz; Ademuz (46001) | `coincide` | El PNG no rotula municipios ni está georreferenciado. |
| `C02` | `1N|1S` | Culla (12051) / Atzeneta del Maestrat (12001) | `coincide` | La línea oficial tiene grosor y antialiasing. |
| `C03` | `1N|2` | Rossell (12096) / Canet lo Roig (12036) | `coincide` | No se pueden identificar términos individuales en el PNG. |
| `C04` | `1S|2` | Alfondeguilla (12007) / la Vall d'Uixó (12126) | `coincide` | Comparación visual, no medición cartográfica. |
| `C05` | `1S|3` | Jérica (12071) / Altura (12012) | `coincide` | Generalización y grosor de línea a 500 px. |
| `C06` | `2|4` | la Vall d'Uixó (12126) / Sagunt (46220) | `coincide` | Etiquetas próximas y trazo negro ocultan detalles finos. |
| `C07` | `3|4` | Albalat dels Tarongers (46010) / Sagunt (46220) | `coincide` | La marca de agua y el código 4 reducen legibilidad local. |
| `C08` | `3|5` | Tous (46246) / Alzira (46017) | `coincide` | La referencia no muestra nombres municipales. |
| `C09` | `4|5` | Cullera (46105) / Tavernes de la Valldigna (46238) | `coincide` | Resolución y antialiasing de la línea costera. |
| `C10` | `5|6` | Xixona/Jijona (03083) / Alacant/Alicante (03014) | `coincide` | La línea oficial no permite medir desplazamientos subpíxel. |
| `C11` | `3|5` | Hueco de zona 3 y componente enclavado de Alzira (46017), zona 5 | `coincide` | La marca de agua y los rótulos 3/4 ocultan parte del contorno. |
| `C12` | `4` | Discontinuidades de zona 4: Sagunt (46220) y València (46250) | `coincide_con_limitacion` | Tres componentes miden menos de un píxel a esta escala. |
| `C13` | `2|4|5|6` | Pequeñas partes costeras e insulares de zonas 2, 4, 5 y 6 | `coincide_con_limitacion` | La ausencia visual de una microparte subpíxel no prueba ausencia cartográfica. |
| `C14` | `1N|6` | Extremos norte y sur | `coincide` | Lectura manual del borde antialiasado. |
| `C15` | `1N|1S|2|3|4|5|6` | Costa completa y posición relativa de las siete zonas | `coincide` | El PNG es una representación gráfica no georreferenciada de 500×835 px. |

El detalle completo de evidencia geométrica, evidencia visible y limitaciones consta en `control-points.csv`.

## Discrepancias

Resultado: 3 explicables, 0 corregibles y 0 bloqueantes.

| ID | Ubicación / zonas | Clasificación | Evidencia | Origen posible | Decisión |
|---|---|---|---|---|---|
| `D01` | Microcomponentes costeros e insulares de zonas 2, 4, 5 y 6 / 2, 4, 5, 6 | `explicable` | La geometría conserva 29, 5, 67 y 154 partes; varias proyectan menos de un píxel y no pueden distinguirse individualmente en la referencia. | imagen o versión oficial; transformación exclusivamente visual usada en GEO-004 | Conservar todas las partes canónicas; no filtrar ni modificar geometría. |
| `D02` | Costa y fronteras internas en toda la Comunitat / 1N, 1S, 2, 3, 4, 5, 6 | `explicable` | Se observan diferencias locales de grosor/antialiasing y posibles desplazamientos subpíxel, sin contradicción de asignación o forma. | imagen o versión oficial; geometría ICV; transformación exclusivamente visual usada en GEO-004 | No cuantificar como diferencia cartográfica; usar composición y detalles para inspección cualitativa. |
| `D03` | Centro: zonas 3, 4 y enclave de 5 / 3, 4, 5 | `explicable` | La marca de agua y las etiquetas cubren parte de los contornos finos en la referencia. | imagen o versión oficial | Apoyar la revisión con render limpio y vista ampliada; no inferir una frontera oculta. |

No se encontró contradicción material atribuible a la asignación 112CV, al crosswalk GEO-002, a la geometría ICV, a la reparación limitada de Xàtiva, a la disolución o a la reproyección GEO-003. No se propone repetir GEO-002 o GEO-003.

## Composición, superposición y detalles

- Render independiente: `render/zones-exact-1000x1670.png` (1000×1670 px).
- Render registrado: `render/zones-registered-500x835.png` (500×835 px).
- Lado a lado: `comparison/side-by-side.png` (1020×835 px).
- Superposición semitransparente: `comparison/overlay.png` (500×835 px).
- Detalles: norte/Rincón, hueco central/zona 4, costa oriental/componentes y extremo sur.

La composición muestra la misma silueta general, posición relativa, costa, Rincón, fronteras principales, hueco de 3/enclave de 5 y extremos. La superposición confirma la equivalencia visual con diferencias locales explicables por trazo, antialiasing, resolución, etiquetas, marca de agua y posible versión cartográfica.

## Reproducibilidad

```sh
.venv-geo/bin/python tools/geo_compare.py build
.venv-geo/bin/python tools/geo_compare.py validate
.venv-geo/bin/python -m unittest tests.test_geo_compare -v
```

Versiones fijadas/observadas:

- geos: `3.13.1`.
- numpy: `2.5.1`.
- pillow: `11.3.0`.
- pillow_libjpeg: `6.2`.
- pillow_zlib: `1.3.1.zlib-ng`.
- proj: `9.5.1`.
- pyproj: `3.7.2`.
- python: `3.13.2`.
- python_implementation: `CPython`.
- shapely: `2.1.2`.
- sqlite: `3.51.2`.
- zlib_compile: `1.2.12`.
- zlib_runtime: `1.2.12`.

Todos los PNG se serializan con Pillow fijado, compresión PNG nivel 9, sin metadatos temporales. Orden de zonas, dimensiones, rellenos diagnósticos, contornos, rótulos, recortes, escalas y transformación están fijados en `config/geo_compare.json`. `validate` regenera y exige igualdad byte a byte.

## Conclusión y aprobación

La evidencia preparada es compatible con aprobar que la geometría derivada representa materialmente las mismas siete zonas que el mapa oficial.

**Aprobación registrada:** Usuario de la sesión (identidad no proporcionada) — 2026-07-18. Decisión: “Apruebo la geometría.”

Geometría congelada para el MVP: `sha256:e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0`. TILES-001 debe consumir exactamente esa versión como entrada inmutable.

También siguen abiertas la confirmación formal de que PREVIFOC sea exactamente una unión de municipios completos y la licencia específica 112CV (`not_found`).
