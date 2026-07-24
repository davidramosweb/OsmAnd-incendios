# GEO-003 — Disolver municipios y validar las siete zonas

**Estado:** completado  
**Dependencias:** [GEO-002](./GEO-002-crosswalk-municipal.md)  
**Siguiente:** [GEO-004](./GEO-004-comparacion-visual.md)

## Objetivo

Generar una geometría canónica reproducible para las siete zonas PREVIFOC mediante la disolución de los municipios aprobados.

## Contexto

La geometría será derivada de fuentes oficiales, no una capa PREVIFOC publicada directamente. Deben conservarse costa, huecos, enclaves y multipolígonos.

## Alcance

- Unir geometría municipal y crosswalk por el código oficial aprobado.
- Validar y documentar cualquier reparación geométrica necesaria.
- Disolver por ID 53–59 sin rellenar huecos.
- Conservar una versión maestra en el CRS de origen y exportar GeoJSON RFC 7946 en EPSG:4326.
- Calcular bbox, área, número de partes y hashes por zona.
- Verificar cobertura total y ausencia de solapes materiales entre zonas.

## Fuera de alcance

- Comparación con los JPEG oficiales.
- Simplificación por zoom.
- Estilos o colores.
- Teselas.

## Entregables

- Geometría maestra con siete entidades.
- `zones.geojson` con IDs y códigos estables.
- Informe topológico y de áreas.
- Comando reproducible de generación.

## Criterios de aceptación

- [x] La entrada contiene los 542 municipios aprobados.
- [x] La salida contiene exactamente siete `MultiPolygon` válidos y no vacíos.
- [x] La unión de las siete zonas equivale a la unión municipal dentro de una tolerancia documentada.
- [x] Las intersecciones entre zonas no tienen área material.
- [x] Ninguna isla, enclave o hueco se elimina sin justificación.
- [x] El GeoJSON usa longitud/latitud y cumple RFC 7946.
- [x] Misma entrada y versiones de herramientas producen los mismos hashes.

## Verificación

Inspeccionar las siete zonas en un visor GIS, con atención especial a costa, Rincón de Ademuz, límites 1N/1S, zona 4 y discontinuidades territoriales.

## Cierre de sesión

Anotar versiones de herramientas, tolerancias y reparaciones aplicadas. GEO-004 usará esta salida sin modificarla.

## Cierre de GEO-003 — 2026-07-18

### Implementación y entregables

- Configuración fijada: `config/geo_zones.json`.
- Dependencias exactas: `requirements-geo.txt`.
- Herramienta offline: `python3 tools/geo_zones.py build` y `validate`.
- Geometría maestra: `data/zones/zones.gpkg`, capa `zones`, siete entidades
  `MULTIPOLYGON` en EPSG:25830.
- Exportación: `data/zones/zones.geojson`, RFC 7946 en longitud/latitud
  EPSG:4326, sin miembro `crs` y con nueve decimales.
- Procedencia, estadísticas y versiones: `data/zones/manifest.json`.
- Informe topológico y de áreas: `data/zones/REPORT.md`.
- Pruebas unitarias y aceptación real: `tests/test_geo_zones.py`.
- Uso y entorno documentados en `tools/README.md`.

Hashes finales:

- `zones.gpkg`: `e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0`.
- `zones.geojson`: `b76ffaeec4eb9c75ee23991ed9386136d74d94a5bc2603700d65b37e6fb528c2`.

### Entradas y unión

- Se ejecutaron y exigieron, antes de leer geometrías,
  `python3 tools/geo_sources.py validate` y
  `python3 tools/geo_crosswalk.py validate`.
- Se volvió a calcular el SHA-256 de `crosswalk.csv` y coincidió con
  `0ca0ed22ccaaa6994d4701bd75da1d1355fcb945f4e7dfaf1b22472743294876`.
- `icv_cod_ine_mun` y `cod_ine_mun` se conservaron como texto de cinco
  dígitos, incluidos los ceros iniciales.
- Unión bidireccional: 542 códigos ICV y 542 códigos del crosswalk, 542
  correspondencias; cero ICV sin crosswalk y cero crosswalk sin ICV.
- No se reinterpretó, corrigió ni resolvió ninguna correspondencia nominal.
- Los conteos 53–59 siguen siendo 28, 64, 40, 113, 61, 190 y 46.

### Inspección y reparación municipal

Las 542 geometrías se inspeccionaron antes de disolver: 541 eran válidas y
Xàtiva (`46145`) era inválida por
`Self-intersection[709369.141817707 4318531.9671089]`. Dos miembros del
`MultiPolygon` compartían un segmento de 5,589746953170743 m, que no está
permitido entre miembros distintos.

Solo a Xàtiva se aplicó
`shapely.make_valid(method="linework", keep_collapsed=True)`. La componente
poligonal válida conserva toda la superficie; el segmento común queda
registrado como `LineString` de área cero. Efectos:

- partes poligonales: 30 → 29 por fusión de las dos partes que compartían el
  segmento;
- huecos: 18 → 18;
- bbox: sin cambio;
- diferencia simétrica poligonal: 0 m²;
- diferencia absoluta de área por redondeo numérico:
  `0.00000004470348358154297` m², dentro de tolerancia.

MakeValid `linework` conserva cada borde y vértice. La disminución de una parte
no elimina una isla: combina dos superficies cuya frontera se solapaba; el
tramo lineal colapsado se conserva en el registro de reparación. No se reparó
ninguna geometría válida, no se rellenaron huecos y no se filtró ninguna parte
por tamaño. El snapshot original se abrió en modo de solo lectura y conserva su
SHA-256 crudo.

### Tolerancias y topología

Todas las tolerancias usan
`máximo(absoluta, relativa × área de referencia)`:

- cobertura: `0.0001` m² absoluta y `1e-12` relativa;
- intersección por par: `0.0001` m² absoluta y `1e-12` relativa respecto al
  área de la menor zona;
- reparación: `0.0001` m² absoluta y `1e-12` relativa;
- control adicional de ida/vuelta GeoJSON: `10` m² absoluta y `1e-9`
  relativa, por el redondeo determinista acumulado a nueve decimales.

Resultados:

- unión municipal: `23272224413.487911` m²;
- unión de las siete zonas: `23272224413.488121` m²;
- diferencia simétrica: `0` m²; tolerancia efectiva de cobertura:
  `0.023272224413` m²;
- 21 pares de zonas comprobados; solape máximo: `0` m²;
- ida/vuelta GeoJSON: entre `5.128811260` y `8.533710233` m² por zona, todas
  por debajo de 10 m²;
- siete geometrías maestras y siete GeoJSON válidos, no vacíos y de tipo
  `MultiPolygon`.

Estadísticas por zona:

| ID | Código | Municipios | Área (m²) | Partes | Huecos | SHA-256 WKB canónico |
|---:|---|---:|---:|---:|---:|---|
| 53 | `1N` | 28 | 1993550921.701355 | 1 | 0 | `972053c8ca188f112680ad50815da68468c47f38154da238893f9caee8bd2f72` |
| 54 | `1S` | 64 | 2324474549.651284 | 1 | 0 | `a7c410cab864c51dc4fe759ee83d8953873186d51e27ac3f1ce212da68bcb001` |
| 55 | `2` | 40 | 2083519624.843262 | 29 | 0 | `bc31a8f1c3fa5adcec3f1318ca14d07f5f50f5610bd1617e8fb8774711cbfff9` |
| 56 | `3` | 113 | 8067376020.863291 | 2 | 1 | `b9d3c784c6ecda35551b1f9d307361662e4ad0e1b36afa3c1344a8e6390cc213` |
| 57 | `4` | 61 | 1030739322.335906 | 5 | 0 | `1356a386be519cc52b9f3f9ccffa5f5811f9e9c6baefe8c070779dd8beea8222` |
| 58 | `5` | 190 | 5423915816.108098 | 67 | 0 | `7a1e31a631d3f09c454db64049e6d06358bf3ed6bdaaa0234c6f6abbce903892` |
| 59 | `6` | 46 | 2348648157.985292 | 154 | 0 | `d4066ce1b2695c3ff7f0572bddd1fa3760da772108ba3274db3e3e41fb8ec6e2` |

Los bboxes EPSG:25830 y EPSG:4326 completos constan en el manifiesto y el
informe.

### Determinismo y versiones

Las filas se ordenan por código e ID; anillos, huecos y partes tienen
orientación, inicio y orden canónicos; no hay simplificación; atributos y JSON
usan orden fijo; el GeoPackage usa metadatos y timestamp fijados. Dos
ejecuciones consecutivas de `validate` reprodujeron los hashes anteriores y
exigieron igualdad byte a byte.

Versiones exactas usadas:

- CPython 3.13.2;
- Shapely 2.1.2;
- GEOS 3.13.1 / GEOS C API 1.19.2;
- pyproj 3.7.2;
- PROJ 9.5.1;
- NumPy 2.5.1;
- SQLite 3.51.2;
- certifi 2026.6.17, dependencia fijada de pyproj.

### Pruebas y verificaciones ejecutadas

- `python3 tools/geo_sources.py validate`.
- `python3 tools/geo_crosswalk.py validate`.
- `python3 tools/geo_zones.py build`.
- Dos ejecuciones consecutivas de `python3 tools/geo_zones.py validate` con
  hashes idénticos.
- `python3 -m py_compile tools/geo_zones.py tests/test_geo_zones.py`.
- `python3 -m unittest tests.test_geo_zones -v`: 6 pruebas correctas.
- `python3 -m unittest discover -s tests -v`: 20 pruebas correctas, incluidas
  las 14 heredadas de GEO-001/GEO-002 y la aceptación real de GEO-003.
- `PRAGMA integrity_check`: `ok`; `application_id`: GeoPackage; capa `zones`:
  siete filas y `MULTIPOLYGON` EPSG:25830.
- Inspección independiente de RFC 7946: siete IDs 53–59, sin `crs`, posiciones
  finitas `[longitud, latitud]`, anillos exteriores antihorarios y huecos
  horarios.

Los fixtures incluyen reparación, huecos, partes pequeñas, multipolígonos,
solapes, cobertura incompleta, CRS, ejes/orientación RFC 7946, GeoPackage y
repetibilidad.

### Inspección visual

Se renderizó localmente `zones.gpkg` exacto, sin simplificación y con vistas de
detalle. Resultado:

- costa completa sin truncamientos ni picos gruesos;
- las pequeñas partes costeras de las zonas 2, 4, 5 y 6 siguen presentes;
- Rincón de Ademuz se conserva como el segundo componente separado de zona 3;
- el límite 1N/1S es continuo y sin huecos o solapes visibles;
- zona 4 conserva su corredor principal y sus cinco componentes, incluidas las
  discontinuidades costeras;
- el único hueco de zona 3 contiene correctamente el componente enclavado de
  zona 5;
- no aparecieron errores de renderizado.

La inspección no abrió ni comparó `previfoc.jpeg`, `zonasprevifoc.png` ni ningún
otro mapa oficial; esa comparación queda para GEO-004.

### Decisiones, desviaciones y condiciones para GEO-004

- Se introdujeron Shapely/GEOS y pyproj/PROJ porque el entorno no disponía de
  biblioteca o CLI geoespacial. Las versiones y dependencias transitivas quedan
  fijadas y manifestadas.
- La reparación de Xàtiva fue necesaria, no silenciosa, limitada a la única
  geometría inválida y sin cambio material de superficie.
- No hubo contradicciones entre GEO-003, GEO-002, el crosswalk aprobado y los
  datos fijados; no quedan bloqueos técnicos para cerrar GEO-003.
- La licencia específica de 112CV continúa en estado `not_found` y debe
  resolverse antes de reutilización pública.
- Sigue sin existir confirmación formal de que PREVIFOC sea exactamente una
  unión de municipios completos. La salida se describe como
  `derived_from_official_municipal_assignment`, no como polígono PREVIFOC
  oficial.
- GEO-004 debe consumir estas salidas sin modificarlas y realizar la comparación
  externa con los mapas oficiales. GEO-003 no ha generado estilos, colores,
  teselas ni simplificaciones por zoom.
