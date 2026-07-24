# GEO-001 — Obtener y fijar las fuentes geográficas

**Estado:** completado  
**Dependencias:** ninguna  
**Siguiente:** [GEO-002](./GEO-002-crosswalk-municipal.md)

## Objetivo

Crear un proceso reproducible que descargue y conserve las dos entradas necesarias para construir las zonas: la asignación municipal PREVIFOC del 112CV y la cartografía municipal oficial del ICV.

## Contexto

Los endpoints PREVIFOC no incluyen polígonos. El endpoint `municipios` asigna los 542 municipios valencianos a los IDs de zona 53–59. El ICV aporta los límites municipales oficiales. En este ticket no se unen ambas fuentes ni se generan zonas.

Leer antes: [DATA_SOURCES.md](../DATA_SOURCES.md), especialmente las secciones `municipios` y cartografía ICV.

## Alcance

- Elegir y documentar una URL oficial estable para cada entrada.
- Implementar un comando local de descarga con timeout, identificación del cliente y errores claros.
- Guardar cuerpo original, URL, fecha UTC, cabeceras relevantes y SHA-256.
- Inspeccionar automáticamente formato, CRS, capa y campos disponibles de la cartografía.
- Crear fixtures pequeños o metadatos suficientes para probar sin descargar siempre las fuentes completas.

## Fuera de alcance

- Correspondencias por nombre.
- Disolución de municipios.
- Reproyección o simplificación.
- Teselas.
- Automatización en Cloudflare.

## Entregables

- Herramienta local de descarga documentada.
- Snapshot crudo de `municipios` y snapshot/versionado de la geometría ICV.
- Manifiesto JSON con URL, hash, recuperación, licencia declarada, formato, capa y CRS.
- Informe con conteos y campos observados.

## Criterios de aceptación

- [x] La fuente 112CV contiene exactamente 542 municipios asignados a 53–59 más `Fuera C.V.`.
- [x] La fuente ICV contiene 542 geometrías municipales no vacías.
- [x] Se identifica el campo de nombre y, si existe, el código municipal oficial.
- [x] El CRS y la licencia quedan registrados sin inferencias silenciosas.
- [x] Dos ejecuciones con el mismo contenido producen el mismo hash.
- [x] Un error HTTP o un archivo inesperado termina con código distinto de cero y no sustituye el último snapshot válido.

## Verificación

Ejecutar la descarga desde un directorio limpio, revisar el manifiesto y comprobar manualmente al menos Ademuz, València y un municipio con denominación bilingüe.

## Cierre de sesión

Anotar las rutas y hashes que debe consumir GEO-002, además de cualquier diferencia entre los campos esperados y los realmente publicados.

## Cierre de GEO-001 — 2026-07-18

Implementación:

- Configuración reproducible: `config/geo_sources.json`.
- Comando local sin dependencias externas: `python3 tools/geo_sources.py download`.
- Revalidación offline: `python3 tools/geo_sources.py validate`.
- Documentación: `tools/README.md`.
- Pruebas con servidor HTTP y GeoPackage temporales: `tests/test_geo_sources.py`.
- Manifiesto de procedencia: `data/sources/manifest.json`.
- Informe de conteos, campos, CRS y muestras: `data/sources/REPORT.md`.

Snapshots que debe consumir GEO-002:

| Fuente | Ruta | SHA-256 crudo | SHA-256 lógico del dataset |
|---|---|---|---|
| 112CV `municipios` | `data/sources/snapshots/municipios_112cv/5d80c0b9a40c29beca831c964ef11b254d0f5a0c5c765acd77dc355ddd54370d.json` | `5d80c0b9a40c29beca831c964ef11b254d0f5a0c5c765acd77dc355ddd54370d` | `a1a2c18581507e2c19167a5cd9633110abddd8484bf93296be23ee88f54c6d06` |
| ICV `ICV.Municipios` | `data/sources/snapshots/icv_municipios/acf27959034b7ad4610b413a6323f1b68e2e0d6d71d72ed74f25b96c3a1dc276.gpkg` | `acf27959034b7ad4610b413a6323f1b68e2e0d6d71d72ed74f25b96c3a1dc276` | `f384ce5ec703a3f2ed4173337f8d80aa24e502cf015f2a3124f30a29506130df` |

Resultados observados:

- 112CV: 543 filas; 542 municipios únicos en las zonas 53–59 y un único registro exacto `Fuera C.V.`. Campos publicados: `municipio`, `idZonaPrevifoc`, `idZonaAvisoMeteo`, `idZonaEmergencia`.
- ICV: 542 entidades `MULTIPOLYGON`, todas no vacías; capa `ICV.Municipios`; campo de nombre `nom_mun`; código oficial `cod_ine_mun`; CRS declarado `EPSG:25830` (`ETRS89 / UTM zone 30N`).
- Licencia ICV: `CC BY 4.0 Generalitat`, declarada en `ows:AccessConstraints` del WFS y enlazada al catálogo oficial. Para 112CV no se encontró licencia específica publicada; se registra como `not_found`, sin interpretar el acceso público como licencia.
- Revisión manual independiente: Ademuz, València y la denominación bilingüe Alacant/Alicante aparecen en ambas fuentes con las formas detalladas en el informe. Esta inspección no constituye un crosswalk.

Verificaciones ejecutadas:

- `python3 -m py_compile tools/geo_sources.py tests/test_geo_sources.py`.
- `python3 -m unittest discover -s tests -v`: 6 pruebas correctas, incluidas repetibilidad, geometría vacía, HTTP 503, tipo de archivo inesperado y conservación del manifiesto previo.
- Descarga real desde un directorio temporal vacío seguida de `validate`: correcta.
- `python3 tools/geo_sources.py validate` sobre los entregables fijados: correcta.
- La descarga limpia y el snapshot fijado producen las mismas huellas lógicas para ambas fuentes. El JSON produce además el mismo SHA-256 crudo.

Desviación documentada: el WFS del ICV genera el GPKG bajo demanda e introduce una nueva hora en `gpkg_contents.last_change`. Dos peticiones con las mismas 542 entidades tienen por ello distintos bytes y SHA-256 crudos. Se conserva siempre el cuerpo original y su hash; adicionalmente, `inspection.dataset_content_sha256` calcula una huella determinista de esquema, CRS, atributos y geometrías, excluyendo únicamente `fid` y la fecha generados. No se normaliza ni sustituye el snapshot crudo.

Condiciones para GEO-002:

- Usar las rutas y los hashes del manifiesto, nunca las URLs vivas.
- No unir por igualdad o similitud de nombres: 112CV no publica código INE y el ICV expone varias formas lingüísticas.
- La falta de licencia específica publicada para 112CV no impide construir el crosswalk local, pero sigue siendo un bloqueo de reutilización que debe resolverse antes de una publicación pública.
- En GEO-001 no se ha creado el crosswalk, no se han generado las siete zonas y no se han producido teselas.
