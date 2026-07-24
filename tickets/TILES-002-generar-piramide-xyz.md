# TILES-002 — Generar la pirámide XYZ estática z6–14

**Estado:** completado  
**Dependencias:** [TILES-001](./TILES-001-formato-plantilla-indexada.md)  
**Siguiente:** [OSMAND-001](./OSMAND-001-publicar-fuente-prueba.md)

## Objetivo

Convertir la geometría congelada en una pirámide completa de teselas plantilla XYZ, lista para publicación estática y posterior recoloreado.

## Alcance

- Reproyectar a Web Mercator durante el render sin modificar la geometría canónica.
- Enumerar solo las teselas que intersectan las zonas entre z6 y z14.
- Rasterizar rellenos por índice de zona y límites negros.
- Guardar rutas `{z}/{x}/{y}.png` con Y XYZ no invertida.
- Generar una única tesela transparente para peticiones fuera de cobertura.
- Crear manifiesto con versión geométrica, formato, zoom, conteos, bytes y hashes.
- Comprobar que el conjunto completo cabe dentro del límite de assets del MVP.

## Fuera de alcance

- Servir por HTTP.
- Aplicar niveles actuales.
- Generar TMS, MBTiles u otros formatos.

## Entregables

- Directorio de plantillas z6–14.
- Tesela transparente compartida.
- Manifiesto de pirámide.
- Mosaicos o imágenes de control por varios zooms.

## Criterios de aceptación

- [x] Todas las teselas son PNG indexados conformes a TILES-001.
- [x] No se genera ninguna tesela fuera de z6–14.
- [x] El número total de assets del despliegue previsto es inferior a 19.000.
- [x] No hay seams, huecos blancos ni inversiones de Y visibles.
- [x] Las fronteras coinciden entre teselas adyacentes.
- [x] El exterior de la Comunitat es transparente.
- [x] La generación es determinista para la misma `geometry_version`.
- [x] Las teselas permiten distinguir pistas y nombres del mapa base con el alpha acordado.

## Verificación

Crear mosaicos de z6, z10 y z14; revisar costa, límites internos y cuatro esquinas de teselas. Decodificar una muestra automática de cada zoom.

## Cierre de sesión

Registrar conteo y tamaño total. OSMAND-001 publicará exactamente este directorio sin transformarlo.

## Cierre de TILES-002 — 2026-07-18

Se generó exclusivamente `data/tiles-002`, sin iniciar OSMAND-001 ni modificar,
regenerar o sustituir GEO-002/003/004 o los fixtures/manifiesto congelados de
TILES-001. La entrada sigue siendo
`geometry_version = sha256:e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0`
y el formato sigue siendo `previfoc-indexed-template-v1`.

### Barreras e integridad de entrada

Antes de usar la geometría se ejecutaron con éxito las cinco validaciones
exigidas: `geo_sources.py validate`, `geo_crosswalk.py validate`,
`geo_zones.py validate`, `geo_compare.py validate` y
`tile_template.py validate`. También se comprobaron directamente:

- `zones.gpkg`: `e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0`;
- `zones.geojson`: `b76ffaeec4eb9c75ee23991ed9386136d74d94a5bc2603700d65b37e6fb528c2`;
- `crosswalk.csv`: `0ca0ed22ccaaa6994d4701bd75da1d1355fcb945f4e7dfaf1b22472743294876`.

### Conteos y tamaños

| Zoom | Teselas | Bytes |
|---:|---:|---:|
| 6 | 2 | 1.574 |
| 7 | 4 | 3.374 |
| 8 | 8 | 6.916 |
| 9 | 19 | 16.029 |
| 10 | 50 | 37.863 |
| 11 | 151 | 98.315 |
| 12 | 501 | 283.507 |
| 13 | 1.838 | 920.428 |
| 14 | 6.934 | 3.235.218 |
| **Total** | **9.507** | **4.603.224** |

Con `transparent.png`, inventario, informe, manifiesto y cuatro controles hay
9.515 assets y 5.463.911 bytes. Los 9.508 assets previstos de despliegue son
las 9.507 rutas `{z}/{x}/{y}.png` y la única tesela transparente compartida;
ambos conteos quedan por debajo de 19.000.

### Rasterizado y continuidad

`tools/tile_pyramid.py` abre `zones.gpkg` en modo solo lectura y reproyecta las
siete geometrías a EPSG:3857 solo en memoria. Enumera candidatos desde la
envolvente y usa intersección exacta contra las partes poligonales. Y aumenta
hacia el sur; no hay inversión TMS.

Los rellenos se dibujan por separado con índices 1–7 y los anillos originales
se trazan después en negro, índice 8 y 2 px. Cada render usa una rejilla global
Web Mercator, 8 px de overscan y recorte central 256×256. Se compararon contra
un render compartido todas las orientaciones adyacentes existentes por zoom:
17 parejas son idénticas byte a byte. Z6 solo contiene dos teselas en una fila,
por lo que no existe pareja vertical cubierta y no se creó un asset ficticio.

### Controles, contrato y resultado visual

Los mosaicos z6, z10 y z14 y el detalle z14 se montaron desde las teselas
publicadas. La inspección visual confirma norte arriba, costa y extremos en su
posición esperada, siete zonas distinguibles por sus marcadores, límites
internos continuos, fondo transparente, ausencia de huecos blancos y ninguna
línea de tesela visible. El detalle z14 cruza una arista real sin discontinuidad.

Automáticamente se verificaron el extremo costero oriental, diez fronteras
internas, una tesela exterior totalmente transparente, norte Y=6155 frente a
sur Y=6328, 108 píxeles de esquina y cero píxeles blancos visibles. Tres
muestras de cada zoom pasan el contrato TILES-001: 256×256, indexed-8, color 3,
chunks exactos, un IDAT, índices 0–8, `tRNS 00 4d 4d 4d 4d 4d 4d 4d b3` y
alpha 0/77/179. El alpha 77 deja visible el 70 % del mapa base; no se aplicaron
colores finales ni niveles actuales.

Hashes de control:

- `manifest.json`: `5534833f228772b4e25602420cdc51024603b6971d8a58c5ab590649dd8a1972`;
- `tiles.sha256`: `4fd05f73854d7cb620aa1d2721096b54dd1217f29c514f3242448febdb9f1bc0`;
- z6: `de7d2ccec4a316e9ae5047f567f0fd422b4fc56ab88e7266b232751993f1b54b`;
- z10: `568c14598fd8a6c00ea316b9973eb88b00ad24ed184b895c5c42c79a990a4559`;
- z14: `0cb6b8c3dbffedcf58482f3f3dfb839aa10c5e24d16738e132db66d655314e20`;
- detalle de seam z14: `95ed3f83904f3a8ee5ca861fc9dd3e368a9795e4b66bf77fad7e65839428727a`.

### Comandos y pruebas

```sh
.venv-geo/bin/python tools/tile_pyramid.py build
.venv-geo/bin/python tools/tile_pyramid.py validate
.venv-geo/bin/python -m unittest tests.test_tile_pyramid -v
.venv-geo/bin/python -m unittest discover -s tests -v
```

Las diez pruebas específicas cubren enumeración XYZ, z6–14, Y no invertida,
determinismo, contrato PNG, continuidad, exterior transparente, conteos,
manifiesto, inventario, hashes y límite de assets. `validate` regenera toda la
pirámide en un directorio temporal y exige el mismo conjunto de rutas y bytes.
La suite completa pasa 47/47. Su primer intento dentro del sandbox solo falló
porque las seis pruebas heredadas de GEO-001 no podían abrir un servidor local
en `127.0.0.1`; repetida fuera de esa restricción, pasa íntegramente.

No se implementó HTTP, TMS, MBTiles, Worker, caché, Cloudflare, recoloreado
dinámico, niveles actuales, colores finales ni ninguna parte de OSMAND-001.
