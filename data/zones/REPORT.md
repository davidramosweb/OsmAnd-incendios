# GEO-003 — Informe topológico y de áreas

Geometría derivada al disolver la asignación municipal oficial aprobada. No es una capa poligonal PREVIFOC publicada directamente y no se ha comparado con JPEG oficiales (GEO-004).

## Procedencia y barreras

- Crosswalk aprobado: `data/crosswalk/crosswalk.csv`; SHA-256 `0ca0ed22ccaaa6994d4701bd75da1d1355fcb945f4e7dfaf1b22472743294876`; 542 filas.
- Snapshot ICV intacto: `data/sources/snapshots/icv_municipios/acf27959034b7ad4610b413a6323f1b68e2e0d6d71d72ed74f25b96c3a1dc276.gpkg`; SHA-256 `acf27959034b7ad4610b413a6323f1b68e2e0d6d71d72ed74f25b96c3a1dc276`; huella lógica `f384ce5ec703a3f2ed4173337f8d80aa24e502cf015f2a3124f30a29506130df`.
- Capa/campo de unión: `ICV.Municipios.cod_ine_mun` ← `crosswalk.icv_cod_ine_mun`; los códigos se leyeron como texto de cinco dígitos.
- Antes de leer geometrías se ejecutaron y exigieron `python3 tools/geo_sources.py validate` y `python3 tools/geo_crosswalk.py validate`.
- Unión bidireccional: 542 municipios; ICV sin crosswalk=0; crosswalk sin ICV=0.
- No se consultó ninguna URL viva ni se modificó el snapshot crudo.
- Licencia específica 112CV: `not_found`; licencia ICV declarada: CC BY 4.0 Generalitat.

## Inspección y reparación municipal

Se inspeccionaron 542 geometrías antes de disolver: 541 válidas y 1 inválida. Tras la reparación controlada, las 542 son válidas.

| Código | Municipio | Motivo | Operación | Partes | Huecos | Δ área abs. (m²) | Dif. simétrica (m²) |
|---|---|---|---|---:|---:|---:|---:|
| `46145` | Xàtiva | Self-intersection[709369.141817707 4318531.9671089] | `MakeValid linework` | 30→29 | 18→18 | 0.000000044703 | 0.000000000000 |

La única reparación usa GEOS MakeValid en modo `linework`, que conserva cada borde y vértice. En Xàtiva dos partes compartían un segmento de 5,589746953 m: se fusionan en una parte poligonal y el segmento queda registrado como `LineString` de área cero. El bbox y los 18 huecos no cambian; no se elimina ninguna superficie, isla, enclave ni hueco.

## Zonas maestras (EPSG:25830)

| ID | Código | Municipios | Área (m²) | Partes | Huecos | Bbox EPSG:25830 | SHA-256 WKB canónico |
|---:|---|---:|---:|---:|---:|---|---|
| 53 | `1N` | 28 | 1993550921.701355 | 1 | 0 | `721352.979, 4455128.553, 780071.455, 4519161.349` | `972053c8ca188f112680ad50815da68468c47f38154da238893f9caee8bd2f72` |
| 54 | `1S` | 64 | 2324474549.651284 | 1 | 0 | `683987.327, 4406581.266, 748916.082, 4473094.663` | `a7c410cab864c51dc4fe759ee83d8953873186d51e27ac3f1ce212da68bcb001` |
| 55 | `2` | 40 | 2083519624.843262 | 29 | 0 | `730434.175, 4400674.153, 815520.530, 4501523.359` | `bc31a8f1c3fa5adcec3f1318ca14d07f5f50f5610bd1617e8fb8774711cbfff9` |
| 56 | `3` | 113 | 8067376020.863291 | 2 | 1 | `626576.389, 4306793.700, 730536.155, 4452641.114` | `b9d3c784c6ecda35551b1f9d307361662e4ad0e1b36afa3c1344a8e6390cc213` |
| 57 | `4` | 61 | 1030739322.335906 | 5 | 0 | `705047.838, 4331894.462, 740981.392, 4409132.718` | `1356a386be519cc52b9f3f9ccffa5f5811f9e9c6baefe8c070779dd8beea8222` |
| 58 | `5` | 190 | 5423915816.108098 | 67 | 0 | `666334.600, 4245932.000, 781105.710, 4340617.000` | `7a1e31a631d3f09c454db64049e6d06358bf3ed6bdaaa0234c6f6abbce903892` |
| 59 | `6` | 46 | 2348648157.985292 | 154 | 0 | `669653.500, 4190817.426, 747033.111, 4271857.560` | `d4066ce1b2695c3ff7f0572bddd1fa3760da772108ba3274db3e3e41fb8ec6e2` |

Todas las entidades son `MultiPolygon`, válidas, no vacías y se ordenan por `zone_id` 53–59.

### Bbox RFC 7946 (EPSG:4326, longitud/latitud)

| ID | Código | Bbox [oeste, sur, este, norte] |
|---:|---|---|
| 53 | `1N` | `-0.381513886, 40.209054375, 0.310787349, 40.788631201` |
| 54 | `1S` | `-0.846296899, 39.779894609, -0.076146616, 40.375707234` |
| 55 | `2` | `-0.308568311, 39.721921657, 0.690315074, 40.617094935` |
| 56 | `3` | `-1.528811131, 38.891586182, -0.311132193, 40.211683158` |
| 57 | `4` | `-0.617179275, 39.103424466, -0.188453020, 39.801434300` |
| 58 | `5` | `-1.094161755, 38.345402970, 0.234072522, 39.186060965` |
| 59 | `6` | `-1.058611799, 37.843778910, -0.166246616, 38.562769158` |

## Tolerancias y controles topológicos

Las tolerancias combinan un suelo absoluto y una parte relativa: `máximo(absoluta, relativa × área de referencia)`. No se usa tolerancia lineal, simplificación ni eliminación por tamaño.

- Cobertura: absoluta 0.0001 m²; relativa 1e-12. Observada: diferencia simétrica 0.000000000000 m² (0); tolerancia efectiva 0.023272224413 m²; **correcta**.
- Solapes: absoluta 0.0001 m²; relativa 1e-12 respecto a la menor zona del par. Se comprobaron los 21 pares; máximo observado 0.000000000000 m²; **sin solapes materiales**.
- Reparaciones: absoluta 0.0001 m²; relativa 1e-12. La reparación registrada queda dentro de tolerancia.
- GeoJSON ida/vuelta: 9 decimales; absoluta 10.0 m²; relativa 1e-09; las siete zonas pasan.
- Área unión municipal: 23272224413.487911 m²; área unión de zonas: 23272224413.488121 m².

## RFC 7946 y determinismo

`zones.geojson` no incluye miembro `crs`, usa posiciones `[longitud, latitud]` EPSG:4326, anillos exteriores antihorarios, huecos horarios y precisión fija de 9 decimales. Se validaron rangos, tipos, IDs y geometrías no vacías.

Las entradas se ordenan por código e ID; los anillos, huecos y partes se canonicalizan sin simplificar; WKB, atributos y JSON tienen orden fijo; el GeoPackage usa metadatos y timestamp fijados. `validate` regenera en memoria y exige igualdad byte a byte.

- `zones.gpkg` SHA-256: `e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0`.
- `zones.geojson` SHA-256: `b76ffaeec4eb9c75ee23991ed9386136d74d94a5bc2603700d65b37e6fb528c2`.

## Versiones exactas

- geos: `3.13.1`.
- geos_capi: `3.13.1-CAPI-1.19.2`.
- numpy: `2.5.1`.
- proj: `9.5.1`.
- pyproj: `3.7.2`.
- python: `3.13.2`.
- python_implementation: `CPython`.
- shapely: `2.1.2`.
- sqlite: `3.51.2`.

## Condiciones para GEO-004

La geometría queda descrita como `derived_from_official_municipal_assignment`. Sigue sin existir confirmación formal de que PREVIFOC sea exactamente una unión de municipios completos. La comparación externa con los mapas/JPEG oficiales pertenece exclusivamente a GEO-004.
