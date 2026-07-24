# GEO-002 — Construir y revisar el crosswalk municipal

**Estado:** completado  
**Dependencias:** [GEO-001](./GEO-001-obtener-fuentes-geograficas.md)  
**Siguiente:** [GEO-003](./GEO-003-disolver-validar-zonas.md)

## Objetivo

Relacionar cada uno de los 542 nombres publicados por el 112CV con una única entidad municipal del ICV y conservar la asignación PREVIFOC de forma auditable.

## Contexto

El 112CV no publica código INE en `municipios`. Existen artículos pospuestos, apóstrofos y denominaciones bilingües, por lo que una coincidencia aproximada no puede aprobarse automáticamente.

## Alcance

- Normalizar nombres solo para proponer candidatos: Unicode, espacios, mayúsculas, apóstrofos y separadores bilingües.
- Mantener un fichero de alias explícito y versionado para excepciones.
- Generar una tabla con nombre 112CV, ID de zona, entidad ICV, código oficial, método y estado de revisión.
- Producir informes de no encontrados, duplicados y coincidencias ambiguas.
- Exigir revisión humana para cualquier fila que no sea una coincidencia exacta inequívoca.

## Fuera de alcance

- Modificar geometrías.
- Decidir mediante distancia de texto sin revisión.
- Disolver por zona.
- Corregir nombres en las fuentes originales.

## Entregables

- `crosswalk.csv` o formato tabular equivalente con 542 filas.
- Fichero de alias revisable.
- Informe de coincidencias automáticas y manuales.
- Prueba automatizada de unicidad y cobertura.

## Criterios de aceptación

- [x] Hay exactamente 542 filas y ninguna corresponde a `Fuera C.V.`.
- [x] Cada municipio 112CV aparece una vez.
- [x] Cada fila apunta a una única geometría ICV.
- [x] No existen códigos municipales duplicados ni vacíos.
- [x] Los IDs de zona pertenecen exclusivamente a 53–59.
- [x] Los conteos por zona son 28, 64, 40, 113, 61, 190 y 46 para 53–59 respectivamente.
- [x] Toda coincidencia no exacta indica alias, motivo y revisión.
- [x] Regenerar la tabla con las mismas fuentes no cambia el resultado.

## Verificación

Revisar manualmente todas las denominaciones bilingües, artículos pospuestos y filas resueltas mediante alias. Comparar los conteos finales con [DATA_SOURCES.md](../DATA_SOURCES.md).

## Cierre de sesión

Registrar el hash del crosswalk aprobado. GEO-003 no debe aceptar una tabla con filas pendientes de revisión.

## Cierre de GEO-002 — 2026-07-18

Implementación:

- Configuración y procedencia fijada: `config/geo_crosswalk.json`.
- Aliases explícitos: `config/municipality_aliases.json`.
- Registro versionado de revisión: `config/municipality_reviews.csv`.
- Herramienta offline: `python3 tools/geo_crosswalk.py build` y `validate`.
- Crosswalk: `data/crosswalk/crosswalk.csv`.
- Manifiesto e informe: `data/crosswalk/manifest.json` y `data/crosswalk/REPORT.md`.
- Pruebas: `tests/test_geo_crosswalk.py`.
- Uso documentado en `tools/README.md`.

Resultado aprobado:

- SHA-256 de `crosswalk.csv`: `0ca0ed22ccaaa6994d4701bd75da1d1355fcb945f4e7dfaf1b22472743294876`.
- Cobertura: 542/542 nombres 112CV y 542/542 códigos ICV; `Fuera C.V.` se valida y excluye.
- Métodos: 457 igualdades literales con `nom_mun`, 72 igualdades literales con otra variante ICV y 13 aliases explícitos.
- Diagnósticos finales: cero no encontrados, cero coincidencias exactas ambiguas, cero códigos vacíos, duplicados o sin asignar y cero filas pendientes de revisión.
- Conteos por zonas 53–59: 28, 64, 40, 113, 61, 190 y 46.
- Revisión versionada: 86 filas distintas, que cubren las 34 denominaciones bilingües, los 57 artículos pospuestos, los 13 aliases y Ademuz, València y Alacant/Alicante; las categorías se solapan.

Decisiones:

- Solo una igualdad literal inequívoca con una variante nominal ICV puede aprobarse automáticamente.
- La normalización NFKC de Unicode, espacios, caja, apóstrofos y `/` sirve únicamente para proponer candidatos en diagnósticos. No asigna códigos y no se usa distancia de texto.
- Toda fila sin igualdad literal requiere una entrada aprobada en el fichero de aliases y otra en el registro de revisión. La herramienta rechaza aliases redundantes, incompletos o pendientes.
- `cod_ine_mun` se conserva y valida como texto de cinco dígitos; es la clave que debe consumir GEO-003.
- La salida se ordena determinísticamente por el nombre 112CV y `validate` exige igualdad byte a byte con una regeneración en memoria.

Aliases/excepciones introducidos:

| Nombre 112CV | `cod_ine_mun` | Entidad ICV | Motivo resumido |
|---|---|---|---|
| Alfarp | `46026` | Alfarb | Diferencia ortográfica final p/b. |
| Algar de Palancia | `46028` | Algar de Palància | Acento no publicado por 112CV. |
| Alqueries, les/Alquerías del Niño Perdido | `12901` | les Alqueries | Artículo valenciano pospuesto/antepuesto. |
| Camp de Mirra, el/Campo de Mirra | `03051` | el Camp de Mirra | Artículo valenciano pospuesto/antepuesto. |
| Fondó de les Neus, el/Hondón de las Nieves | `03077` | el Fondó de les Neus | Artículo valenciano pospuesto/antepuesto. |
| Novetlè/Novelé | `46180` | Novetlè | El ICV no publica la forma bilingüe completa. |
| Orxa, l'/Lorcha | `03084` | l'Orxa | Artículo apostrofado pospuesto/antepuesto. |
| Pobla de Benifassà, la | `12093` | La Pobla de Benifassà | Posición y caja del artículo. |
| Poble Nou de Benitatxell, el/Benitachell | `03042` | el Poble Nou de Benitatxell | Artículo valenciano pospuesto/antepuesto. |
| Torre de les Maçanes, la/Torremanzanas | `03132` | la Torre de les Maçanes | Artículo valenciano pospuesto/antepuesto. |
| Torre d'en Besora, la | `12119` | la Torre d'En Besora | Posición/caja del artículo y caja de En. |
| Useres, les/Useras | `12122` | les Useres | Artículo valenciano pospuesto/antepuesto. |
| Vila Joiosa, la/Villajoyosa | `03139` | la Vila Joiosa | Artículo valenciano pospuesto/antepuesto. |

Verificaciones ejecutadas:

- `python3 tools/geo_sources.py validate`: las dos entradas y sus hashes de GEO-001 siguen siendo válidos.
- `python3 -m py_compile tools/geo_crosswalk.py tests/test_geo_crosswalk.py`.
- `python3 -m unittest tests.test_geo_crosswalk -v`: 8 pruebas correctas, incluidas repetibilidad, biyección, ceros iniciales, rechazo de normalización automática, ambigüedad, alias pendiente, revisión ausente, salida alterada y hash fuente cambiado.
- `python3 -m unittest discover -s tests -v`: 14 pruebas correctas, incluidas las 6 pruebas heredadas de GEO-001.
- `python3 tools/geo_crosswalk.py build` seguido de dos ejecuciones de `validate`: salida idéntica y mismo SHA-256.
- Inspección manual del informe completo de 86 casos y de las filas de Ademuz, València, Alacant/Alicante y los 13 aliases.

Desviaciones y bloqueos:

- No se encontraron contradicciones entre el ticket, GEO-001 y los snapshots fijados, ni fue necesario desviarse del alcance.
- La licencia específica de 112CV sigue sin publicarse (`not_found`). No bloquea este crosswalk local, pero debe resolverse antes de reutilización pública.
- Sigue sin existir confirmación formal de que las zonas PREVIFOC sean exactamente uniones de términos municipales completos. Es una condición de validación geométrica posterior, no una incertidumbre del crosswalk.
- GEO-003 debe consumir exactamente el crosswalk cuyo hash figura arriba, comprobar que no hay revisiones pendientes y mantener `cod_ine_mun` como texto. GEO-002 no ha disuelto, reproyectado, simplificado ni generado geometrías o teselas.
