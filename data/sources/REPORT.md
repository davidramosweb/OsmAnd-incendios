# GEO-001 — Informe de fuentes fijadas

Generado en UTC: `2026-07-18T06:48:29Z`.

Este informe inspecciona las dos entradas por separado. No crea un crosswalk, no une nombres y no genera zonas.

## Snapshots

| Fuente | Cuerpo original | SHA-256 | Recuperación UTC |
|---|---|---|---|
| 112CV municipios | `snapshots/municipios_112cv/5d80c0b9a40c29beca831c964ef11b254d0f5a0c5c765acd77dc355ddd54370d.json` | `5d80c0b9a40c29beca831c964ef11b254d0f5a0c5c765acd77dc355ddd54370d` | `2026-07-18T06:48:28Z` |
| ICV municipios | `snapshots/icv_municipios/acf27959034b7ad4610b413a6323f1b68e2e0d6d71d72ed74f25b96c3a1dc276.gpkg` | `acf27959034b7ad4610b413a6323f1b68e2e0d6d71d72ed74f25b96c3a1dc276` | `2026-07-18T06:48:29Z` |

La columna SHA-256 anterior identifica los bytes originales. La huella lógica determinista de cada dataset, independiente del orden del JSON y del `last_change` que el WFS inserta al generar cada GPKG, es:

- 112CV: `a1a2c18581507e2c19167a5cd9633110abddd8484bf93296be23ee88f54c6d06`.
- ICV: `f384ce5ec703a3f2ed4173337f8d80aa24e502cf015f2a3124f30a29506130df`.

## 112CV `municipios`

- Formato observado: JSON (`application/json`).
- Filas: 543; municipios asignados: 542; registros `Fuera C.V.`: 1.
- Campos: `idZonaAvisoMeteo`, `idZonaEmergencia`, `idZonaPrevifoc`, `municipio`.
- Conteos por `idZonaPrevifoc`: 53=28, 54=64, 55=40, 56=113, 57=61, 58=190, 59=46.
- Licencia: not_found; No se ha encontrado una licencia especifica ni condiciones de API publicadas; el acceso publico no se interpreta como licencia.

### Muestras observadas (112CV)

| municipio | idZonaPrevifoc | idZonaAvisoMeteo | idZonaEmergencia |
|---|---:|---:|---:|
| Ademuz | 56 | 9 | 21 |
| València | 57 | 10 | 27 |
| Alacant/Alicante | 59 | 4 | 44 |

## ICV `ICV.Municipios`

- Formato observado: OGC GeoPackage (`application/geopackage+sqlite3`).
- Capa: `ICV.Municipios`; geometría: `MULTIPOLYGON` en `geom`.
- Geometrías: 542; no vacías: 542; `integrity_check`: `ok`.
- Campo de nombre seleccionado: `nom_mun`; código municipal oficial: `cod_ine_mun`.
- CRS declarado dentro del GPKG: `EPSG:25830` — ETRS89 / UTM zone 30N.
- Licencia declarada: `CC BY 4.0 Generalitat`. Atribución: Delimitación territorial: Municipios de la Comunitat Valenciana, Institut Cartogràfic Valencià / Generalitat Valenciana, CC BY 4.0.

### Campos observados (ICV)

| Campo | Tipo | Nulo permitido | Clave primaria |
|---|---|---|---|
| `fid` | `INTEGER` | no | sí |
| `geom` | `MULTIPOLYGON` | sí | no |
| `id` | `TEXT` | sí | no |
| `cod_ine_mun` | `TEXT` | sí | no |
| `cod_ine_mun_d` | `TEXT` | sí | no |
| `cod_catastro` | `TEXT` | sí | no |
| `nom_mun` | `TEXT` | sí | no |
| `nom_mun_cas` | `TEXT` | sí | no |
| `nom_mun_cas_a` | `TEXT` | sí | no |
| `nom_mun_val` | `TEXT` | sí | no |
| `nom_mun_val_a` | `TEXT` | sí | no |
| `noms_mun` | `TEXT` | sí | no |
| `comarca` | `TEXT` | sí | no |
| `provincia` | `TEXT` | sí | no |
| `perimetro` | `REAL` | sí | no |
| `area_ha` | `REAL` | sí | no |

### Muestras observadas (ICV)

Estas filas son una inspección independiente y no constituyen correspondencias aprobadas para GEO-002.

| cod_ine_mun | nom_mun | nom_mun_cas | nom_mun_val | noms_mun |
|---|---|---|---|---|
| 46001 | Ademuz | Ademuz | Ademuz | Ademuz |
| 46250 | València | València | València | València |
| 03014 | Alacant | Alicante | Alacant | Alacant/Alicante |

## Observaciones para GEO-002

- Consumir exclusivamente las rutas y hashes del manifiesto, no una URL viva.
- El JSON 112CV no contiene código INE; los nombres no deben unirse por igualdad ni similitud sin una tabla revisada.
- El ICV ofrece nombres en varias formas y `cod_ine_mun`; GEO-002 debe decidir y revisar cada correspondencia.
- La licencia específica de los datos 112CV sigue sin estar publicada o verificada.
- El WFS del ICV genera un `gpkg_contents.last_change` nuevo en cada petición. Por ello dos descargas con las mismas entidades pueden tener distinto SHA-256 crudo; `inspection.dataset_content_sha256` permite comprobar la igualdad lógica sin alterar ni normalizar el snapshot original.
