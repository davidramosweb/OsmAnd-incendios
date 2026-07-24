# Herramientas reproducibles (GEO-001 a OSMAND-001)

## Fuentes fijadas (GEO-001)

`geo_sources.py` descarga las dos entradas oficiales de GEO-001, conserva los cuerpos sin transformar y solo actualiza el manifiesto después de validar ambas fuentes. No instala dependencias: requiere Python 3.10 o posterior con soporte SQLite.

## Descargar

Desde cualquier directorio:

```sh
python3 "/Users/davidramos/Documents/OsmAnd incendios/tools/geo_sources.py" download
```

Para probar en un directorio vacío sin tocar el snapshot del proyecto:

```sh
tmp_dir="$(mktemp -d)"
cd "$tmp_dir"
python3 "/Users/davidramos/Documents/OsmAnd incendios/tools/geo_sources.py" download --output "$tmp_dir/sources"
python3 "/Users/davidramos/Documents/OsmAnd incendios/tools/geo_sources.py" validate --manifest "$tmp_dir/sources/manifest.json"
```

La configuración versionada está en `config/geo_sources.json`. Se puede ajustar el límite total por petición con `--timeout SEGUNDOS` y la identificación con `--user-agent TEXTO`. La herramienta envía siempre `User-Agent` y `Accept`, aplica límites de tiempo y tamaño y muestra los fallos en stderr con código de salida `2`.

## Salidas y promoción segura

- `data/sources/snapshots/<fuente>/<sha256>.<ext>`: cuerpo HTTP original, con nombre direccionado por contenido.
- `data/sources/manifest.json`: URL solicitada y final, UTC de recuperación, cabeceras HTTP relevantes, tamaño, SHA-256 crudo, huella lógica determinista, licencia y resultado de inspección.
- `data/sources/REPORT.md`: conteos, campos, capa, geometría, CRS y muestras observadas.

Las dos respuestas se descargan a un área temporal. Solo si ambas pasan todas las validaciones se conservan los cuerpos por hash y se sustituye atómicamente el manifiesto al final. Un HTTP no exitoso, timeout, JSON inesperado, GPKG inválido, conteo distinto o geometría vacía devuelve código no cero y no cambia el manifiesto válido anterior. Un snapshot con otro hash nunca sobrescribe un cuerpo ya guardado.

El WFS del ICV materializa un `gpkg_contents.last_change` nuevo en cada petición, de modo que dos GPKG con las mismas entidades pueden tener distintos bytes y SHA-256 crudos. El campo `inspection.dataset_content_sha256` calcula además una huella estable de esquema, CRS, atributos y geometrías (ordenada por código municipal y sin el `fid` ni la fecha generados). El JSON obtiene la misma huella sobre sus filas canónicas. El cuerpo original nunca se modifica para conseguirla.

## Revalidar sin red

```sh
python3 tools/geo_sources.py validate
```

La revalidación comprueba el hash y el tamaño de cada cuerpo, el hash de la configuración y vuelve a ejecutar todas las inspecciones. No genera correspondencias municipales, disoluciones, reproyecciones, zonas ni teselas.

## Pruebas

```sh
python3 -m unittest discover -s tests -v
```

Las pruebas levantan un servidor HTTP local y crean un GeoPackage mínimo temporal. Así comprueban descargas repetibles y la protección del último manifiesto válido sin volver a descargar las fuentes completas.

## Crosswalk municipal (GEO-002)

`geo_crosswalk.py` consume exclusivamente `data/sources/manifest.json` y los dos snapshots fijados por GEO-001. No descarga datos, no consulta las URLs registradas y no modifica los snapshots. La procedencia cruda y lógica esperada está fijada en `config/geo_crosswalk.json`.

Construir los entregables:

```sh
python3 tools/geo_crosswalk.py build
```

Regenerarlos en memoria y exigir igualdad byte a byte:

```sh
python3 tools/geo_crosswalk.py validate
```

Salidas:

- `data/crosswalk/crosswalk.csv`: 542 asignaciones con nombre 112CV, zona, código y variantes ICV, método, motivo de alias y estado de revisión.
- `data/crosswalk/manifest.json`: hashes de configuración, aliases, revisiones, manifiesto fuente, snapshots y salidas; también conserva los conteos de aceptación.
- `data/crosswalk/REPORT.md`: procedencia, métodos, conteos, aliases, revisiones y condiciones para GEO-003.

Entradas revisables:

- `config/municipality_aliases.json`: las 13 excepciones no exactas, con código esperado, valores ICV observados, motivo y revisión aprobada.
- `config/municipality_reviews.csv`: revisión explícita de todas las denominaciones bilingües, artículos pospuestos, aliases y muestras mínimas exigidas.

La única resolución automática permitida es una igualdad literal que conduce a una sola fila ICV usando `nom_mun`, `nom_mun_cas`, `nom_mun_cas_a`, `nom_mun_val`, `nom_mun_val_a` o `noms_mun`. Unicode NFKC, espacios, caja, apóstrofos y separadores bilingües se normalizan únicamente para sugerir candidatos en mensajes de error. Una coincidencia normalizada o aproximada nunca asigna un código.

La construcción falla si cambia una huella fijada, aparece `Fuera C.V.` con otra forma, varían los conteos, falta un alias, una igualdad es ambigua, una revisión obligatoria no está aprobada o el resultado no es una biyección entre los 542 nombres y los 542 códigos ICV. Los códigos se validan y escriben como texto de cinco dígitos para conservar ceros iniciales.

Pruebas específicas:

```sh
python3 -m unittest tests.test_geo_crosswalk -v
```

La suite completa sigue disponible con `python3 -m unittest discover -s tests -v` y no usa red.

## Siete zonas canónicas (GEO-003)

`geo_zones.py` consume exclusivamente el crosswalk aprobado de GEO-002 y el
snapshot ICV fijado por GEO-001. No descarga fuentes, no modifica asignaciones
nominales y no altera el GeoPackage original. Antes de leer geometrías ejecuta
y exige las dos barreras previas:

```sh
python3 tools/geo_sources.py validate
python3 tools/geo_crosswalk.py validate
```

Después vuelve a comprobar que `data/crosswalk/crosswalk.csv` tiene SHA-256
`0ca0ed22ccaaa6994d4701bd75da1d1355fcb945f4e7dfaf1b22472743294876`,
mantiene `icv_cod_ine_mun` como texto de cinco dígitos y demuestra la unión
bidireccional 542↔542 con `ICV.Municipios.cod_ine_mun`.

### Entorno reproducible

GEO-003 usa Python 3.13 y las versiones exactas de `requirements-geo.txt`. Para
crear un entorno aislado:

```sh
python3.13 -m venv .venv-geo
.venv-geo/bin/python -m pip install --requirement requirements-geo.txt
```

El manifiesto registra además las versiones enlazadas de GEOS, GEOS C API,
PROJ y SQLite. El entorno usado para congelar los entregables fue CPython
3.13.2, Shapely 2.1.2, GEOS 3.13.1, pyproj 3.7.2, PROJ 9.5.1, NumPy 2.5.1 y
SQLite 3.51.2.

### Construir y validar

```sh
.venv-geo/bin/python tools/geo_zones.py build
.venv-geo/bin/python tools/geo_zones.py validate
```

`validate` regenera los cuatro artefactos y exige igualdad byte a byte. Las
salidas son:

- `data/zones/zones.gpkg`: capa maestra `zones`, siete `MULTIPOLYGON` en
  EPSG:25830;
- `data/zones/zones.geojson`: RFC 7946 en longitud/latitud EPSG:4326, sin
  miembro `crs` y con nueve decimales;
- `data/zones/manifest.json`: procedencia, versiones, tolerancias, hashes,
  reparación, unión, áreas, bboxes, partes, huecos y 21 controles por pares;
- `data/zones/REPORT.md`: informe legible de topología y áreas.

La configuración está fijada en `config/geo_zones.json`. La disolución se hace
en EPSG:25830, sin simplificar, rellenar huecos ni eliminar partes pequeñas. El
orden de entidades, anillos, huecos, partes, atributos y números es canónico.

### Reparación y tolerancias

Las 542 geometrías se inspeccionan antes de disolver. La única invalidez fijada
es Xàtiva (`46145`): dos partes comparten un segmento de 5,589746953 m. Se aplica
solo a esa geometría `shapely.make_valid(method="linework",
keep_collapsed=True)` y se extrae la superficie poligonal; el tramo colapsado se
registra como `LineString` de área cero. Se conservan bbox, superficie y los 18
huecos. Cualquier invalidez nueva o ausencia de la esperada hace fallar la
construcción.

Las tolerancias usan `máximo(absoluta, relativa × área de referencia)`:

- cobertura: 0,0001 m² y `1e-12`;
- solape por par: 0,0001 m² y `1e-12` respecto a la menor zona;
- efecto de reparación: 0,0001 m² y `1e-12`;
- control adicional GeoJSON ida/vuelta: 10 m² y `1e-9`, debido al redondeo
  determinista acumulado sobre todos los vértices.

### Pruebas GEO-003

```sh
.venv-geo/bin/python -m unittest tests.test_geo_zones -v
.venv-geo/bin/python -m unittest discover -s tests -v
```

Los fixtures cubren reparación controlada, conservación de huecos y partes
pequeñas, `MultiPolygon`, detección de solapes y huecos de cobertura, CRS,
orden de ejes y orientación RFC 7946, GeoPackage y repetibilidad. La prueba de
aceptación real valida los cuatro entregables y sus hashes sin usar red.

La inspección visual de GEO-003 se limita a la geometría generada. No abre ni
compara JPEG o mapas oficiales; esa comparación pertenece a GEO-004.

## Comparación visual oficial (GEO-004)

`geo_compare.py` consume sin modificar `data/zones/zones.gpkg`,
`data/zones/zones.geojson`, el crosswalk aprobado y el snapshot original de
`zonasprevifoc.png`. Antes de comparar ejecuta las tres barreras:

```sh
.venv-geo/bin/python tools/geo_sources.py validate
.venv-geo/bin/python tools/geo_crosswalk.py validate
.venv-geo/bin/python tools/geo_zones.py validate
```

El entorno de GEO-004 extiende, sin cambiarlo, el conjunto exacto de GEO-003:

```sh
python3.13 -m venv .venv-geo
.venv-geo/bin/python -m pip install --requirement requirements-geo-004.txt
```

`requirements-geo-004.txt` incluye literalmente `requirements-geo.txt` y fija
Pillow 11.3.0 para serializar los PNG. Construir y revalidar:

```sh
.venv-geo/bin/python tools/geo_compare.py build
.venv-geo/bin/python tools/geo_compare.py validate
.venv-geo/bin/python -m unittest tests.test_geo_compare -v
```

La configuración versionada está en `config/geo_compare.json`. Fija orden,
dimensiones, colores diagnósticos, fuente embebida, posiciones de rótulos,
recortes, escalas y una transformación visual uniforme explicable. El registro
usa escala calculada por la extensión norte-sur, centra horizontalmente las
envolventes e invierte el eje Y. Cuatro controles de extremos quedan por debajo
de 1,5 px; no se aplica ninguna deformación no lineal y no se presenta una
diferencia píxel a píxel como medida cartográfica.

Entregables propios de GEO-004:

- `data/geo-004/snapshots/zonasprevifoc/<sha256>.png`: bytes oficiales
  originales, direccionados por contenido;
- `data/geo-004/reference.json`: URL solicitada/final, UTC, HTTP,
  Content-Type, dimensiones, tamaño, SHA-256 y licencia `not_found`;
- `data/geo-004/render/`: render limpio registrado y versión 2×;
- `data/geo-004/comparison/`: lado a lado y superposición semitransparente;
- `data/geo-004/details/`: ampliaciones norte/Rincón, centro/zona 4, costa y
  extremo sur;
- `data/geo-004/control-points.csv`: municipios/rasgos, evidencia, resultado y
  limitaciones;
- `data/geo-004/discrepancies.json`, `REPORT.md` y `manifest.json`.

`validate` regenera todos los derivados y exige igualdad byte a byte, además de
proteger los hashes congelados de GEO-003. El snapshot original nunca se
sobrescribe. Antes de aprobación explícita, el manifiesto y el informe mantienen
`pending_human_approval`; al aprobarse registran revisor, fecha y
`geometry_version`, que TILES-001 debe consumir como entrada inmutable.

## Plantilla PNG indexada (TILES-001)

`tile_template.py` consume como barrera, sin modificarla, la geometría aprobada
`sha256:e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0`.
Antes de construir o validar comprueba la aprobación de GEO-004 y los SHA-256
directos de `zones.gpkg`, `zones.geojson` y `crosswalk.csv`. No regenera ninguna
entrada GEO ni crea la pirámide XYZ.

Construir y validar los tres fixtures de 256×256:

```sh
.venv-geo/bin/python tools/tile_template.py build
.venv-geo/bin/python tools/tile_template.py validate
.venv-geo/bin/python -m unittest tests.test_tile_template -v
```

El contrato congelado es `previfoc-indexed-template-v1`: PNG indexado de 8 bits,
color tipo 3, no entrelazado, con exactamente `IHDR`, `PLTE`, `tRNS`, un `IDAT`
y `IEND`, en ese orden. `PLTE` mide 27 bytes y tiene nueve entradas; `tRNS` mide
9 bytes. Los índices son: 0 fondo, 1–7 zonas 53–59 en orden y 8 límites negros.
Los RGB 1–7 de la plantilla (`#112233` a `#778899`) son marcadores reemplazables,
no colores de producto.

La conversión alpha exacta usa `floor(fracción × 255 + 0.5)`: fondo 0; zonas
30 % → 77 (`0x4D`); límite 70 % → 179 (`0xB3`). Por tanto `tRNS` queda fijado a
`00 4d 4d 4d 4d 4d 4d 4d b3`.

Recolorear una plantilla conforme:

```sh
.venv-geo/bin/python tools/tile_template.py recolor entrada.png salida.png \
  --colors '#112233' '#223344' '#334455' '#445566' '#556677' '#667788' '#778899'
```

El recoloreador analiza chunks y CRC, sustituye solo las siete tripletas RGB de
`PLTE[1:8]`, recalcula el CRC de `PLTE` y exige que `IDAT` sea idéntico. No
decodifica ni recomprime el ráster. `inspect` muestra orden, longitudes, CRC,
hash de `IDAT` e índices usados:

```sh
.venv-geo/bin/python tools/tile_template.py inspect data/tiles-001/fixture-original.png
```

Los artefactos y hashes están en `data/tiles-001/manifest.json` y la
especificación legible en `data/tiles-001/REPORT.md`. La prueba visual usa solo
dos zonas rectangulares sintéticas, un límite común de tres píxeles, bordes
duros y fondo transparente. Pillow 11.3.0 y el decodificador independiente de
la herramienta validan los mismos índices y bytes RGBA. No hay antialias,
etiquetas, iconos, patrones, estilo final, Worker, caché ni teselas XYZ.

## Pirámide XYZ estática (TILES-002)

`tile_pyramid.py` consume exclusivamente `data/zones/zones.gpkg` con la
`geometry_version` congelada y reutiliza `tile_template.encode_indexed_png`,
`validate_contract` y `decode_indexed_png`. Antes de construir o validar ejecuta
las cinco barreras completas:

```sh
.venv-geo/bin/python tools/geo_sources.py validate
.venv-geo/bin/python tools/geo_crosswalk.py validate
.venv-geo/bin/python tools/geo_zones.py validate
.venv-geo/bin/python tools/geo_compare.py validate
.venv-geo/bin/python tools/tile_template.py validate
```

Construir una vez y revalidar mediante regeneración completa temporal:

```sh
.venv-geo/bin/python tools/tile_pyramid.py build
.venv-geo/bin/python tools/tile_pyramid.py validate
.venv-geo/bin/python -m unittest tests.test_tile_pyramid -v
```

La herramienta abre la capa `zones` en modo solo lectura y exige EPSG:25830.
La reproyección a EPSG:3857 existe solo en memoria durante el render. Enumera
el rango candidato por zoom y consulta un índice espacial exacto para escribir
solo polígonos que intersectan la tesela. Las rutas usan XYZ real
`{z}/{x}/{y}.png`: Y crece hacia el sur y nunca se transforma a TMS.

Cada polígono se rasteriza en una rejilla global Web Mercator con máscara de
relleno por zona; los anillos originales se dibujan al final con índice 8 y
ancho 2 px. Una ventana incluye 8 px de overscan en cada lado y publica solo el
recorte central 256×256. Esto aleja del asset los extremos creados al recortar
geometría. La validación compara teselas individuales con los recortes de una
ventana compartida horizontal o vertical, de modo que la continuidad se exige
byte a byte en todas las orientaciones adyacentes existentes por zoom.

Salidas en `data/tiles-002`:

- directorios `6/` a `14/` con 9.507 plantillas conformes;
- `transparent.png`, una única respuesta exterior compartida;
- `tiles.sha256`, inventario por ruta y hash de las 9.507 teselas;
- `manifest.json` y `REPORT.md`, con conteos, bytes, hashes, versiones y
  verificaciones;
- `controls/z6-overview.png`, `z10-overview.png`, `z14-overview.png` y
  `z14-seam-detail.png`, montados desde los PNG publicados.

La verificación de producción decodifica tres muestras por zoom, revisa las
cuatro esquinas, costa, diez límites internos, orientación norte-sur,
transparencia exterior, ausencia de blanco y 17 parejas adyacentes. Z6 solo
tiene dos assets en una fila y, por tanto, no posee pareja vertical cubierta.
No se generan assets ficticios para cubrir esa dirección.

## Fuente XYZ temporal (OSMAND-001)

`osmand_xyz_server.py` sirve exclusivamente la pirámide congelada de TILES-002
por `/tiles/{z}/{x}/{y}.png`. Al arrancar valida manifiesto, inventario,
tesela transparente, las 9.507 rutas y todos sus hashes. Para una coordenada
XYZ válida sin cobertura reutiliza los bytes exactos de `transparent.png`; no
genera, recolorea, recomprime ni escribe PNG.

```sh
.venv-geo/bin/python tools/osmand_xyz_server.py validate
.venv-geo/bin/python tools/osmand_xyz_server.py serve --host 127.0.0.1 --port 8765
```

El origen aplica CORS público y caché temporal de cinco minutos y registra las
peticiones como JSONL en stdout. Zoom, enteros y límites del mundo se validan
antes de acceder a una ruta. Los errores son texto plano 400/404 y no HTML.

Con el origen en ejecución, la matriz HTTP completa se prueba así:

```sh
.venv-geo/bin/python tools/osmand_http_check.py http://127.0.0.1:8765
.venv-geo/bin/python tools/osmand_http_check.py \
  https://mcp.davidramosweb.com/osmand-001 --require-https --print-magic-url
```

El segundo comando comprueba el endpoint HTTPS final e imprime la URL mágica
de OsmAnd. La configuración reproducible de publicación, pasos Android/iOS,
coordenadas por zoom, logging y la limitación de dispositivo físico están en
`deploy/osmand-001/README.md`. OSMAND-001 no incorpora Worker, Cron, KV, caché
persistente, recoloreado ni `.osf`.
