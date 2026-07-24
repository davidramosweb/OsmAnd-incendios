# TILES-001 — Formato PNG indexado congelado

**Versión:** `previfoc-indexed-template-v2`  
**Geometría consumida:** `sha256:e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0`

## Contrato binario

PNG 256×256, profundidad 8, color tipo 3 (indexado), compresión 0, filtro 0 e interlace 0 en IHDR. El archivo contiene exactamente un chunk de cada tipo y en este orden: `IHDR` (13 bytes), `PLTE` (48), `tRNS` (16), `IDAT` y `IEND` (0). Cada CRC-32 se calcula sobre `tipo || datos`.

`PLTE` tiene dieciséis tripletas. Los índices 1–7 son rellenos base, 8–14 son las bandas diagonales de esas mismas zonas y 15 representa límites. El Worker asigna el mismo RGB a ambas variantes para hoy y oscurece 8–14 para mañana. El recoloreador sustituye únicamente esas catorce entradas y el CRC de PLTE; IDAT permanece idéntico.

## Alpha exacto

La conversión fijada es `floor(fracción × 255 + 0.5)` (redondeo half up): fondo 0 % → `0`, los catorce índices de zona 30 % → `77` y límites 70 % → `179`.

## Fixture y limitaciones

El único ráster de prueba con contenido es sintético: dos zonas rectangulares, bandas diagonales globales, fondo 0 y límites en índice 15. No usa geometría geográfica, etiquetas, iconos ni antialias. El fixture transparente usa solo índice 0.

## Fixtures

- `fixture-original.png`: SHA-256 `6e8c1c7eb5d181531f37d3faab560037fae673475d8f9e5285407e257f6a76c4`, 559 bytes.
- `fixture-recolored.png`: SHA-256 `10894b834447ca155dc3457592648473cd52cf65f6025ed0fb375d1dc9770ae9`, 559 bytes.
- `fixture-transparent.png`: SHA-256 `679644f8ef3768bbe373bc2db7d50c3d9f133013cb927154fc920a4471616809`, 229 bytes.

El `IDAT` compartido por original/recoloreado mide 414 bytes y tiene SHA-256 `3f76225c49a0f5e8fe5cd95908ae6cc8ca06b8257d261899fba11faf9db0400d`.

## Comandos

```sh
.venv-geo/bin/python tools/tile_template.py build
.venv-geo/bin/python tools/tile_template.py validate
.venv-geo/bin/python -m unittest tests.test_tile_template -v
.venv-geo/bin/python tools/tile_template.py recolor entrada.png salida.png --colors '#112233' '#223344' '#334455' '#445566' '#556677' '#667788' '#778899'
```

`validate` comprueba primero la aprobación y los hashes congelados de GEO-004/GEO-003, regenera los artefactos en memoria y exige igualdad byte a byte. Las pruebas decodifican con Pillow y con un decodificador PNG independiente basado en la biblioteca estándar.

## Entrada congelada

- `zones.gpkg`: `e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0`.
- `zones.geojson`: `b76ffaeec4eb9c75ee23991ed9386136d74d94a5bc2603700d65b37e6fb528c2`.
- `crosswalk.csv`: `0ca0ed22ccaaa6994d4701bd75da1d1355fcb945f4e7dfaf1b22472743294876`.
- `data/geo-004/manifest.json`: `5c0066a83f255323196121003b0164f1e2bb80ed8bb01125c75592ca1847375e`.
