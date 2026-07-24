# GEO-004 — Comparar y aprobar la geometría frente al mapa oficial

**Estado:** completado  
**Dependencias:** [GEO-003](./GEO-003-disolver-validar-zonas.md)  
**Siguiente:** [TILES-001](./TILES-001-formato-plantilla-indexada.md)

## Objetivo

Demostrar que las siete geometrías derivadas representan materialmente las mismas zonas que el mapa oficial aportado como referencia.

## Contexto

La imagen oficial rotula `1N`, `1S`, `2`, `3`, `4`, `5` y `6`. No tiene coordenadas geográficas utilizables directamente, así que la comparación combina revisión visual, puntos característicos y asignación municipal.

## Alcance

- Renderizar las siete zonas con contornos y códigos sobre fondo blanco.
- Ajustar encuadre y proporción para compararlas con la imagen oficial.
- Crear una composición lado a lado y, si es viable, una superposición semitransparente.
- Revisar puntos característicos, costa y fronteras internas.
- Documentar discrepancias y clasificarlas como explicables, corregibles o bloqueantes.
- Obtener aprobación explícita de la geometría antes de continuar.

## Fuera de alcance

- Cambiar municipios de zona sin corregir primero el crosswalk.
- Digitalizar la imagen para sustituir la cartografía.
- Diseñar todavía las teselas definitivas.

## Entregables

- Imagen renderizada equivalente a la referencia.
- Comparativa visual conservable en el repositorio.
- Lista de puntos/municipios de control.
- Informe de aprobación o bloqueo.

## Criterios de aceptación

- [x] La posición relativa y forma general de las siete zonas coincide con la referencia.
- [x] `1N`, `1S`, `2`, `3`, `4`, `5` y `6` están asignadas correctamente.
- [x] No existe ninguna discrepancia material sin explicación.
- [x] Las discrepancias encontradas se rastrean hasta fuente, crosswalk o versión cartográfica.
- [x] La geometría queda declarada congelada para el MVP mediante hash/versionado.

## Verificación

La revisión debe incluir, como mínimo, una persona y un registro de fecha. Si se cambia el crosswalk o la geometría, deben repetirse GEO-003 y GEO-004.

## Cierre de sesión

Registrar `geometry_version`. TILES-001 debe tratar la geometría como entrada inmutable.

## Cierre de GEO-004 — 2026-07-18

La comparación técnica fue aprobada explícitamente. El ticket queda cerrado y
TILES-001 puede consumir exclusivamente la versión congelada indicada abajo.

### Barreras y entradas congeladas

Se ejecutaron correctamente, antes de comparar:

```sh
.venv-geo/bin/python tools/geo_sources.py validate
.venv-geo/bin/python tools/geo_crosswalk.py validate
.venv-geo/bin/python tools/geo_zones.py validate
```

Hashes comprobados y no modificados:

- `zones.gpkg`: `e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0`;
- `zones.geojson`: `b76ffaeec4eb9c75ee23991ed9386136d74d94a5bc2603700d65b37e6fb528c2`;
- `crosswalk.csv`: `0ca0ed22ccaaa6994d4701bd75da1d1355fcb945f4e7dfaf1b22472743294876`.

### Referencia y entregables

Se fijó exclusivamente la referencia oficial prioritaria documentada:

`https://wpr.112cv.gva.es/external/api/storage/descargar/imagen/static/images/avisosmeteorologicos/zonasprevifoc.png`

- URL final idéntica; HTTP 200; `image/png`; 500×835 px; 44.982 bytes;
- recuperación UTC `2026-07-18T08:14:20Z`;
- SHA-256 `df1c7c08765bcdae51a36d4efbd414911b975d75de878a04faf364cc8b905f7f`;
- bytes originales en almacenamiento direccionado por contenido;
- licencia específica 112CV conservada como `not_found`.

No se usaron buscadores, copias de terceros ni los JPEG secundarios. Los
entregables están aislados en `data/geo-004`: snapshot/metadatos, render limpio
1× y 2×, composición lado a lado, superposición semitransparente, cuatro vistas
ampliadas, 15 controles versionados, informe de discrepancias y manifiesto con
hashes.

### Método y resultado

`tools/geo_compare.py` dibuja todos los vértices y partes exactos de GEO-003,
sin simplificación, filtrado, relleno de huecos ni cambio de coordenadas. El
registro con el PNG usa únicamente escala uniforme, traslación e inversión de
Y. Se fijaron cuatro puntos de control (extremos norte, sur, oeste e isla
oriental); el residuo máximo es 0,645 px. No hay deformación no lineal ni se usa
una diferencia píxel a píxel como medida cartográfica.

La revisión cubre posición/forma de las siete zonas, códigos, costa, Rincón de
Ademuz, 1N/1S, las cinco partes de zona 4, hueco de 3/enclave de Alzira en 5,
partes costeras/insulares de 2/4/5/6, extremos y nueve pares municipales a ambos
lados de fronteras principales.

Discrepancias registradas: tres `explicable`, cero `corregible` y cero
`bloqueante`. Se limitan a microcomponentes subpíxel, trazo/antialiasing o
posible versión cartográfica y ocultación por etiquetas/marca de agua. No se
encontró contradicción material rastreable al 112CV, crosswalk GEO-002,
geometría ICV, reparación de Xàtiva, disolución/reproyección GEO-003 o registro
visual GEO-004.

### Reproducibilidad

Entorno: CPython 3.13.2; Shapely 2.1.2; GEOS 3.13.1; pyproj 3.7.2; PROJ 9.5.1;
NumPy 2.5.1; SQLite 3.51.2; Pillow 11.3.0. `requirements-geo.txt` no se cambió;
`requirements-geo-004.txt` lo incluye y añade Pillow fijado.

```sh
.venv-geo/bin/python tools/geo_compare.py build
.venv-geo/bin/python tools/geo_compare.py validate
.venv-geo/bin/python -m unittest tests.test_geo_compare -v
```

Las siete pruebas específicas de GEO-004 pasan, incluida repetición byte a byte
de renders, dimensiones, transformación, códigos, snapshot y protección contra
cambio de hashes de GEO-003. La suite completa pasa 27 pruebas; las seis pruebas
de GEO-001 que abren un servidor HTTP local se ejecutaron fuera del sandbox tras
el bloqueo esperado de sockets locales en la primera ejecución.

### Aprobación registrada

- Persona revisora: usuario de la sesión (identidad no proporcionada).
- Fecha de revisión: 2026-07-18.
- Decisión explícita: “Apruebo la geometría.”
- `geometry_version` congelada: `sha256:e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0`.

Los hashes congelados de `zones.gpkg`, `zones.geojson` y `crosswalk.csv` se
volvieron a comprobar antes del cierre. TILES-001 debe consumir exactamente la
`geometry_version` anterior como entrada inmutable; no debe regenerar ni alterar
GEO-002/GEO-003.
