# Plan técnico — capa PREVIFOC para OsmAnd

Estado: **investigación y diseño; no implementado**.
Fecha de corte de la investigación: **2026-07-17**.

## 1. Resultado de viabilidad

El proyecto es **técnicamente viable sin fork de OsmAnd**, con dos límites que deben comunicarse desde el principio:

1. La mejor capa común a Android e iOS es XYZ ráster. Se actualiza remotamente, pero sus polígonos no son pulsables y OsmAnd no ofrece una leyenda dinámica fija para una fuente personalizada.
2. PREVIFOC informa del nivel de riesgo, no demuestra por sí solo que una pista concreta esté abierta o cerrada. Los endpoints inspeccionados no contienen resoluciones extraordinarias ni restricciones espaciales. El MVP debe mostrar el riesgo y, para circulación, “no determinado por esta fuente” salvo que se incorpore una fuente jurídica oficial adicional.

La geometría no aparece en los endpoints. Puede obtenerse, sin digitalización manual, mediante los 542 municipios asignados a zona por el 112CV y los límites municipales oficiales del ICV. El resultado será una geometría **derivada de fuentes oficiales**, pendiente de confirmación y validación visual contra el mapa oficial.

## 2. Alcance del MVP

### Incluido

- estado actual y previsión del día siguiente por las siete zonas PREVIFOC;
- geometría derivada y versionada;
- GeoJSON canónico;
- teselas XYZ PNG transparentes para Android e iOS;
- fecha de fuente, fecha de recuperación, calidad y obsolescencia;
- leyenda accesible y señalización cartográfica de stale/sin datos;
- paquete `.osf` de instalación;
- API mínima y consulta por coordenada;
- conservación de última versión válida, validación y alertas;
- atribución y aviso de servicio no oficial.

### No incluido en el MVP

- prometer que una vía está abierta basándose solo en nivel 1/2;
- convertir automáticamente nivel 3 en cierre general;
- navegación o desvíos automáticos dentro de OsmAnd;
- ficha al tocar un polígono ráster;
- ingesta completa de bandos municipales, cierres de parques o resoluciones no estructuradas;
- mapa vectorial OBF diario;
- aplicación móvil o fork de OsmAnd.

## 3. Requisitos verificables

| Requisito | Solución MVP | Limitación |
|---|---|---|
| Zonas PREVIFOC | Disolución de municipios ICV según asignación 112CV | Confirmar que coincide con la definición oficial |
| Nivel vigente | `nact` resuelto contra `situacion` | Campo fuente no documentado formalmente |
| Previsión | `npre` como periodo separado | No confundir con estado vigente |
| Transparencia | PNG32 con alpha 18–32 % | OsmAnd puede añadir transparencia global |
| Leyenda | `legend.png`, enlace OSF y simbología en mapa | No queda fija en la UI de OsmAnd |
| Actualización | fuente XYZ estable + expiración de teselas | Se refresca al visualizar, no necesariamente en background |
| Android e iOS | XYZ + `.osf` | Validación física pendiente |
| Información al pulsar | `/status` fuera de la interacción ráster | OsmAnd no consulta atributos del ráster |
| Circulación | campo separado, solo con evidencia jurídica | PREVIFOC por sí solo no informa “abierto/cerrado” |

## 4. Comparación de arquitecturas

Escala: 1 = muy desfavorable, 5 = muy favorable. Los pesos reflejan el objetivo principal: una capa actualizable y común a OsmAnd Android/iOS.

| Criterio | Peso | A. XYZ | B. WMS/WMTS | C. GeoJSON | D. Descargable | E. Híbrida |
|---|---:|---:|---:|---:|---:|---:|
| Compatibilidad Android+iOS | 25 % | 5 | 2 | 1 | 4 | 5 |
| Actualización automática | 20 % | 5 | 3 | 1 | 1 | 5 |
| Interacción con polígonos | 10 % | 1 | 1 | 4 fuera de OsmAnd | 2 | 3 vía API/web |
| Ruta futura contra restricciones | 10 % | 2 | 3 | 5 | 4 | 5 |
| Sencillez operativa | 10 % | 4 | 2 | 4 | 3 | 3 |
| Rendimiento/consumo | 10 % | 4 | 4 | 3 | 4 | 4 |
| Caché y escalabilidad | 10 % | 5 | 4 | 4 | 3 | 5 |
| Coste inicial | 5 % | 4 | 2 | 5 | 4 | 4 |
| **Puntuación ponderada** | **100 %** | **81/100** | **52/100** | **54/100** | **60/100** | **89/100** |

Las notas no son mediciones absolutas; sirven para hacer explícita la decisión. La compatibilidad final depende del smoke test descrito en `OSMAND_COMPATIBILITY.md`.

Desglose cualitativo de todas las dimensiones solicitadas:

| Dimensión | A. XYZ | B. WMS/WMTS | C. GeoJSON | D. Descargable | E. Híbrida |
|---|---|---|---|---|---|
| Compatibilidad Android | Alta y documentada | Baja/condicionada a adaptador | No como capa dinámica | Alta para formatos OsmAnd | Alta mediante XYZ |
| Compatibilidad iOS | Alta y documentada | Baja/condicionada a template XYZ | No como capa dinámica | Alta para formatos importables | Alta mediante XYZ |
| Actualización automática | Alta al caducar teselas visibles | Media; depende del adaptador | No dentro de OsmAnd | Baja; nueva importación/descarga | Alta para XYZ/API |
| Interacción con polígonos | Nula | Nula en OsmAnd | Alta fuera de OsmAnd | Limitada y dependiente del formato | Alta mediante web/API; nula en el ráster |
| Rendimiento | Alto con teselas precalculadas | Alto, con más render dinámico | Alto para siete zonas | Alto una vez instalado | Alto; cada salida se especializa |
| Consumo de datos | Medio y cacheable | Medio | Bajo para este conjunto | Alto al descargar, nulo offline | Medio y cacheable |
| Facilidad de despliegue | Media | Baja; servidor OGC adicional | Alta | Media; pipeline de paquetes | Media |
| Coste de infraestructura | Bajo | Medio-alto | Bajo | Bajo-medio | Bajo-medio |
| Complejidad operativa | Baja-media | Alta | Baja | Media | Media; exige coherencia atómica |
| Caché | Excelente por URL de tesela | Buena, pero claves más complejas | Excelente como objeto | Por versión del archivo | Excelente para artefactos; corta en API |
| Escalabilidad | Alta mediante CDN | Alta con infraestructura GIS | Alta para el volumen previsto | Limitada por distribución/versiones | Alta mediante CDN + objetos |
| Dependencia de OsmAnd | Baja; contrato XYZ común | Media-alta por su adaptación | Baja, pero no cumple el cliente | Alta para OBF/SQLite/OSF | Baja; GeoJSON/API sobreviven al cliente |
| Ruta futura contra restricciones | Baja sin vector paralelo | Media fuera de OsmAnd | Alta | Media-alta según formato | Alta mediante GeoJSON/API espacial |

“Actualización automática” significa actualización remota de la capa cuando OsmAnd vuelve a solicitar teselas caducadas, no sincronización garantizada en segundo plano.

### Alternativa A — XYZ ráster

**Diseño:** el backend cruza estado y geometrías, renderiza PNG transparentes y publica `/tiles/{z}/{x}/{y}.png`.

Ventajas:

- soporte documentado en Android e iOS;
- actualización al caducar teselas;
- buen rendimiento con CDN;
- configuración sencilla por URL o `.osf`;
- el cliente no procesa geometrías.

Inconvenientes:

- no hay objetos pulsables ni `GetFeatureInfo`;
- consume más almacenamiento/datos que vector;
- cambios diarios requieren nueva pirámide o render bajo demanda;
- la leyenda/fecha no pueden fijarse como panel en OsmAnd;
- por sí sola no sirve para intersecar rutas.

Coste/operación: bajo-medio. Con siete zonas, precomputar z6–14 solo cuando cambie el snapshot y servir por CDN es manejable.

### Alternativa B — WMS o WMTS

Ventajas:

- estándares GIS; estilos y leyenda centralizados;
- WMS puede exponer `GetFeatureInfo` a clientes que lo implementen;
- GeoServer/MapServer resuelven reproyección y render.

Inconvenientes:

- OsmAnd no documenta alta directa de WMS/WMTS ni lectura de capacidades;
- WMS exige adaptar bbox/tamaño a teselas; el formato SQLite menciona un proxy;
- WMTS solo ayuda si se reduce a template Web Mercator equivalente a XYZ;
- GeoServer añade JVM, configuración, actualizaciones y superficie operativa innecesarias;
- la interacción WMS no llega a OsmAnd.

Coste/operación: medio-alto para un problema de siete polígonos. Publicarlo como interfaz adicional futura es razonable; no como contrato móvil principal.

### Alternativa C — GeoJSON dinámico

Ventajas:

- conserva geometría y propiedades;
- ideal para web, QA, API e intersección de rutas;
- pequeño y fácil de versionar;
- puede ser pulsable en clientes web/GIS.

Inconvenientes:

- no es una capa dinámica importable documentada en OsmAnd Android/iOS;
- una importación manual, si alguna versión la acepta, no resolvería actualización ni estilo común;
- puede ser pesado sin simplificación, aunque aquí solo hay siete zonas.

Coste/operación: bajo. Debe existir como salida canónica, pero no satisface por sí solo OsmAnd.

### Alternativa D — paquete descargable

Variantes:

- SQLite ráster compatible con OsmAnd;
- OBF vectorial;
- `.osf` que incluya o sugiera descargas.

Ventajas:

- uso offline predecible;
- OBF puede integrar objetos y estilo;
- distribución controlada y versionada.

Inconvenientes:

- actualización manual o semimanual;
- riesgo de que el usuario mantenga una copia caducada;
- generación OBF añade complejidad y dependencia de herramientas OsmAnd;
- MBTiles no es el SQLite nativo documentado por OsmAnd.

Coste/operación: medio. Útil como fallback offline, no como canal vigente principal.

### Alternativa E — combinación

Componentes:

- XYZ para OsmAnd;
- GeoJSON y metadata como contrato canónico;
- `/status` para una coordenada;
- `.osf` para instalación;
- archivo offline opcional en el futuro.

Ventajas:

- maximiza compatibilidad sin sacrificar datos vectoriales;
- permite CDN para el tráfico pesado y API ligera para interacción;
- prepara intersección de rutas;
- reduce dependencia de OsmAnd.

Inconvenientes:

- varios artefactos deben compartir versión y reglas;
- publicación atómica y pruebas de coherencia son obligatorias;
- la interacción ocurre fuera del ráster de OsmAnd.

**Recomendación:** alternativa E, con XYZ como interfaz móvil principal.

## 5. Modelo de datos normalizado

### Entidades

#### `SourceSnapshot`

```json
{
  "snapshot_id": "sha256:…",
  "source_updated_at": "2026-07-17T00:00:02+02:00",
  "source_updated_at_raw": "2026-07-17 00:00:02.0",
  "retrieved_at": "2026-07-17T11:30:00Z",
  "source_timezone_assumption": "Europe/Madrid",
  "source_urls": [],
  "source_hashes": {},
  "geometry_version": "sha256:…",
  "schema_version": "1.0.0",
  "is_stale": false,
  "source_unreachable": false
}
```

La zona horaria se marca como suposición mientras el 112CV no la confirme.

#### `ZoneStatus`

Campos mínimos y extensiones propuestas:

| Campo | Tipo | Regla |
|---|---|---|
| `zone_id` | string | ID interno estable, por ejemplo `previfoc:53` |
| `source_zone_id` | integer | 53–59 |
| `zone_name` | string | `1N`, `1S`, `2`, `3`, `4`, `5`, `6` |
| `period` | enum | `current` o `forecast_next_day` |
| `risk_level` | integer/null | 1, 2 o 3, derivado de una situación válida |
| `risk_code` | string | Código interno, p. ej. `PREVIFOC_L3_DRY_POSSIBLE` |
| `source_situation_id` | integer | `nact` o `npre` original |
| `dry_storm_risk` | enum | `none`, `possible`, `high`, `unknown` |
| `display_color` | object/string | Color y alpha de presentación; no semántica jurídica |
| `circulation_status` | enum | Ver reglas siguientes |
| `restriction_summary` | string/null | Texto respaldado por evidencia; no inferido del nivel |
| `valid_from` | datetime | Fuente o derivado; declarar procedencia |
| `valid_until` | datetime | Fuente o derivado; declarar procedencia |
| `source_updated_at` | datetime | Momento mostrado por 112CV |
| `retrieved_at` | datetime | Reloj del sistema en UTC |
| `source_url` | URL | URL exacta de la fuente de estado |
| `geometry` | MultiPolygon | EPSG:4326 en GeoJSON |
| `geometry_version` | string | Referencia a geometría, para no acoplarla al estado |
| `data_quality` | object | Procedencia y validaciones |
| `is_stale` | boolean | Nunca inferir actualidad desde `retrieved_at` solamente |

Ejemplo conceptual:

```json
{
  "zone_id": "previfoc:59",
  "source_zone_id": 59,
  "zone_name": "6",
  "period": "current",
  "risk_level": 3,
  "risk_code": "PREVIFOC_L3_DRY_NONE",
  "source_situation_id": 7,
  "dry_storm_risk": "none",
  "display_color": { "hex": "#FF0000", "alpha": 0.30, "pattern": "diagonal" },
  "circulation_status": "not_determined",
  "restriction_summary": "Riesgo extremo. PREVIFOC no acredita por sí solo el cierre de pistas.",
  "valid_from": "2026-07-17T00:00:00+02:00",
  "valid_until": "2026-07-18T00:00:00+02:00",
  "source_updated_at": "2026-07-17T00:00:02+02:00",
  "retrieved_at": "2026-07-17T11:30:00Z",
  "source_url": "https://wpr.112cv.gva.es/external/api/storage/descargar/json/previfoc",
  "geometry_version": "sha256:…",
  "data_quality": {
    "status": "official_source",
    "geometry": "derived_from_official_municipal_boundaries",
    "validity": "calendar_day_inferred",
    "legal_restrictions": "not_ingested"
  },
  "is_stale": false
}
```

El ejemplo ilustra el esquema, no es una afirmación de que el 2026-07-17 tuviera la vigencia horaria indicada oficialmente; el JSON de origen no incluye `valid_until`.

#### `RestrictionNotice`

Entidad separada necesaria antes de mostrar abierto/restringido/cerrado:

```text
restriction_id
authority
legal_basis
source_url
published_at
effective_from / effective_until
scope_type: zone | municipality | protected_area | track | geometry
scope_ids / geometry
activities: foot | bicycle | motor_vehicle | work | fire_use | all
rule: permitted | restricted | prohibited
exceptions
official_text
retrieved_at
is_stale
```

No debe crearse una restricción sintética a partir de `risk_level`.

### Traducción del riesgo

| IDs situación | `risk_level` | `dry_storm_risk` | Etiqueta |
|---|---:|---|---|
| 1, 2, 3 | 1 | none/possible/high | Riesgo bajo/medio |
| 4, 5, 6 | 2 | none/possible/high | Riesgo alto |
| 7, 8, 9 | 3 | none/possible/high | Riesgo extremo |

La traducción se acepta solo si la fila resuelta tiene `ID_AVISO = 3`, está activa y su descripción es compatible. Si la descripción y el bloque discrepan, se rechaza la publicación.

### Estado de circulación

Enum propuesto:

- `permitted`: una fuente oficial aplicable confirma que la actividad y vía están permitidas;
- `restricted`: existe restricción parcial vigente y verificable;
- `prohibited`: existe prohibición vigente y verificable;
- `not_determined`: las fuentes disponibles informan riesgo pero no resuelven circulación;
- `unknown_stale`: la evidencia necesaria está caducada o no disponible.

Reglas de precedencia:

1. Si los datos jurídicos aplicables están stale, `unknown_stale`.
2. Una prohibición oficial vigente y aplicable prevalece: `prohibited`.
3. Una limitación oficial vigente: `restricted`.
4. Un permiso explícito vigente: `permitted`, sin sobreescribir otras normas de rango o ámbito superior.
5. Sin evidencia jurídica: `not_determined`, sea cual sea PREVIFOC.

Nivel 3 puede activar prohibiciones concretas sobre fuego, trabajos o autorizaciones deportivas según normativa, y puede coexistir con resoluciones temporales de acceso. Eso no autoriza a rotular toda el área como “circulación prohibida”. Véanse el [Decreto 91/2023](https://dogv.gva.es/datos/2023/07/07/pdf/2023_7436.pdf) y ejemplos de [medidas extraordinarias de 2022](https://dogv.gva.es/datos/2022/08/12/pdf/2022_7696.pdf). La revisión jurídica de vigencia y alcance queda fuera de la inferencia técnica.

## 6. Arquitectura propuesta

Descripción detallada y diagrama en `ARCHITECTURE.md`.

### Selección tecnológica

| Decisión | Elección MVP | Justificación |
|---|---|---|
| Lenguaje | TypeScript sobre Node.js LTS | Un solo lenguaje para ingesta, dominio, CLI, API, render y tests |
| API | Fastify + Zod | Contratos tipados, validación, serialización, OpenAPI y consulta puntual |
| HTTP | `fetch` nativo | Timeouts mediante `AbortSignal`, cabeceras, reintentos acotados y tests sin otro cliente base |
| Geodatos | GDAL/OGR CLI + Turf | GPKG/WFS, CRS, topología y disolución robustas fuera del runtime; GeoJSON y punto-en-polígono en TypeScript |
| Render | SVG por metatiles + Sharp, sujeto a benchmark | PNG transparente, patrones, etiquetas, antialias y una implementación TypeScript reemplazable |
| Base de datos | Sin PostGIS; GPKG/GeoJSON + objetos versionados | Solo siete zonas y estados diarios; menor operación |
| Almacenamiento | S3 compatible, inicialmente R2 | Última válida, historial y publicación versionada |
| Contenedor | Docker | Fija Node.js, GDAL/OGR y Sharp/libvips, y permite migrar proveedor |
| CI | GitHub Actions | Tests y build; no único cron de producción |
| Ejecución MVP | Render web + cron, misma imagen | Servicio y tarea programada con poco plumbing |
| CDN | Cloudflare | Caché de teselas/JSON y dominio estable |

TypeScript orquesta GDAL/OGR como procesos externos con argumentos controlados; no se incorporan bindings nativos de GDAL para Node. No se propone Tippecanoe para el MVP: generaría vector tiles que OsmAnd no consume como overlay. No se propone GeoServer porque WMS/WMTS no resuelve la compatibilidad móvil y añade operación. MapLibre se reservará para un visor web.

## 7. API pública mínima

Todas las respuestas JSON incluyen:

```json
{
  "schema_version": "1.0.0",
  "snapshot_id": "sha256:…",
  "source_updated_at": "…",
  "retrieved_at": "…",
  "is_stale": false,
  "official": false
}
```

### `/health`

- **Propósito:** salud operativa, no semántica cartográfica.
- **Respuesta 200:** proceso vivo, snapshot cargado, edad, último éxito por fuente.
- **Respuesta 503:** no existe ningún snapshot válido o el servicio no puede leerlo.
- **Caché:** `no-store`.
- **Stale:** 200 con `status: "degraded"` si puede servir la última válida; 503 si nunca tuvo datos válidos.

Ejemplo:

```json
{
  "status": "degraded",
  "snapshot_id": "sha256:…",
  "is_stale": true,
  "sources": { "previfoc": { "last_success_at": "…", "consecutive_failures": 4 } }
}
```

### `/metadata.json`

- **Propósito:** estado global, vigencia, fuentes, atribución, licencia, calidad y disclaimer.
- **Formato:** JSON.
- **Caché:** 60 s, ETag de snapshot.
- **Errores:** 503 si no hay versión válida; 500 solo ante fallo interno.
- **Stale:** 200 con `is_stale=true`, `stale_since`, `stale_reason` y advertencia visible.

### `/zones.geojson`

- **Propósito:** FeatureCollection actual para web/GIS y base de QA.
- **Formato:** RFC 7946, EPSG:4326 implícito.
- **Propiedades:** todos los campos normalizados excepto textos internos no públicos.
- **Caché:** 5 min, ETag; objetos versionados internos inmutables.
- **Errores:** 503 sin snapshot; 406 si se pide formato no soportado.
- **Stale:** se mantiene 200 para no borrar el mapa; cada feature y colección lo indican.

### `/zones/{zone_id}.json`

- **Propósito:** estado detallado de una zona, periodos y evidencia.
- **Formato:** JSON, geometría opcional mediante `?geometry=true`.
- **Caché:** 5 min, ETag.
- **Errores:** 404 zona inexistente; 400 ID mal formado; 503 sin datos.
- **Stale:** 200 con advertencia.

### `/status?lat={lat}&lon={lon}`

- **Propósito:** punto-en-polígono y estado aplicable.
- **Formato:** JSON con `coverage`, zona, estado actual, previsión y restricciones verificadas.
- **Caché:** `no-store` inicialmente; después, 60 s si se normaliza la clave.
- **Errores:** 422 coordenadas fuera de rango; 503 sin snapshot.
- **Fuera de la Comunitat:** 200 con `coverage=false`, no 404.
- **En frontera:** respuesta determinista con `boundary=true`; no elegir al azar si dos geometrías tocan.
- **Stale:** 200 con `circulation_status=unknown_stale`; nunca una respuesta verde silenciosa.

Ejemplo conceptual:

```json
{
  "coverage": true,
  "boundary": false,
  "zone_id": "previfoc:56",
  "risk_level": 3,
  "circulation_status": "not_determined",
  "restriction_summary": "PREVIFOC informa riesgo extremo; consulte restricciones oficiales aplicables.",
  "is_stale": false,
  "official": false
}
```

### `/tiles/{z}/{x}/{y}.png`

- **Propósito:** overlay OsmAnd.
- **Formato:** PNG32 256×256.
- **Rango:** z6–14; fuera del área se sirve tesela transparente 200 para evitar reintentos.
- **Caché:** 5 min en ruta estable, ETag; versión interna inmutable un año.
- **Errores:** 400/404 para coordenadas o zoom inválidos; 503/tesela “sin datos” si nunca hubo snapshot.
- **Stale:** tesela válida con trama y marca “DATOS OBSOLETOS”; cabecera `Warning: 110 - "Response is stale"` si el stack la conserva.

### `/legend.png`

- **Propósito:** leyenda idéntica a la simbología, atribución, fecha y estado stale.
- **Formato:** PNG accesible de alta densidad; añadir también `/legend.json` en una mejora menor.
- **Caché:** 5 min, ETag.
- **Stale:** versión visual específica, no conservar una leyenda verde antigua.

### `/osmand/previfoc.osf`

- **Propósito:** instalar fuente, icono, atribución y enlaces.
- **Formato:** ZIP renombrado `.osf`, `Content-Disposition: attachment`.
- **Caché:** 1 día; cambia solo al modificar la configuración.
- **Errores:** 404 si se retira una versión incompatible; 500 si el paquete no pasa validación.
- **Stale:** sigue siendo descargable porque configura la URL, pero su descripción debe explicar que la disponibilidad se comprueba en metadatos.

## 8. Representación cartográfica

Los colores base coinciden con la web oficial inspeccionada, pero la semántica no depende solo del color.

| Nivel | Riesgo | Color base | Alpha fill | Borde | Patrón/accesibilidad |
|---:|---|---|---:|---|---|
| 1 | Bajo/medio | `#A4CC87` | 0,18 | verde oscuro 1 px | sin trama; etiqueta `1` |
| 2 | Alto | `#FF9800` | 0,25 | marrón oscuro 1,5 px discontinuo | puntos espaciados; etiqueta `2` |
| 3 | Extremo | `#FF0000` | 0,30 | granate 2 px continuo | diagonal fina; etiqueta `3` |
| Sin datos | Desconocido | gris | 0,18 | gris 1,5 px | cruzado + `?` |
| Stale | Dato obsoleto | conserva nivel bajo velo gris | ≤0,25 | gris oscuro | diagonal repetida + texto |

Separar riesgo y circulación:

- una restricción verificada añade borde negro/rojo y símbolo textual `RESTRINGIDO` o `PROHIBIDO`;
- el rojo PREVIFOC nunca se rotula automáticamente `PROHIBIDO`;
- el verde nunca se rotula automáticamente `ABIERTO`.

### Zoom

- z6–7: contorno autonómico, siete códigos, nivel y actualización general; sin detalle municipal.
- z8–9: etiquetas de zona, nivel y símbolo de tormenta `P`/`A` con leyenda textual.
- z10–12: relleno y borde; etiquetas muy espaciadas para no tapar caminos.
- z13–14: relleno más tenue y borde preciso; sin repetir fecha ni etiquetas grandes.
- >z14: OsmAnd sobreescala la última tesela; validar que el resultado es aceptable.

### Accesibilidad

- nivel escrito junto al color;
- patrones diferentes y bordes distinguibles para deuteranopia/protanopia;
- símbolos `P` y `A` acompañados por texto en la leyenda;
- contraste WCAG AA en textos de leyenda y página, probado con simuladores y usuarios;
- no usar rojo/verde como único indicador;
- versión bilingüe ES/VA o leyenda con ambos idiomas;
- alt text en página web y equivalente JSON de la leyenda;
- no animaciones ni parpadeo.

El mapa base debe conservar pistas, caminos y nombres. Por eso el fill tiene alpha bajo, no se renderizan carreteras en la capa y se insta a mantener “Mostrar símbolos del mapa” en iOS.

## 9. Seguridad, legalidad y fiabilidad

### Endpoints no documentados

Aunque son públicos y los usa la web oficial, no constituyen una API contractual. Riesgos:

- cambio de campos o rutas sin aviso;
- bloqueo por frecuencia o WAF;
- publicación parcial durante una actualización;
- ausencia de SLA y contacto;
- licencia de redistribución no explícita.

Mitigaciones:

- adaptadores aislados y contract tests;
- fixtures y hash de esquema;
- carga baja, backoff y `User-Agent` de contacto;
- última versión válida y publicación atómica;
- observación previa de 14 días;
- contacto formal con 112CV/ICV.

### Atribución y licencia

Propuesta de texto, pendiente de aprobación:

> Riesgo: datos reutilizados de 112CV / Generalitat Valenciana, consultados en la fecha indicada. Geometría derivada de “Delimitación territorial: Municipios de la Comunitat Valenciana”, ICV / Generalitat Valenciana, CC BY 4.0. Servicio independiente y no oficial.

Cada respuesta conserva URL, actualización de fuente y recuperación. La geometría ICV tiene licencia confirmada; la reutilización de JSON 112CV debe aclararse antes de producción.

### Responsabilidad

Aviso obligatorio:

> Esta capa es una reutilización no oficial y puede contener errores o retrasos. No sustituye las alertas, resoluciones, señalización, indicaciones de agentes ni información de 112CV y autoridades competentes. Ante discrepancia, prevalece siempre la fuente y señalización oficial. En una emergencia, llame al 112.

No usar logos ni diseño que sugieran servicio oficial. No emitir notificaciones “ruta segura” o “circulación permitida” sin una base jurídica y espacial suficiente.

### Seguridad técnica

- dependencias fijadas y escaneo de imagen Docker;
- R2 privado; credenciales con permisos mínimos y rotación;
- API pública solo lectura; administración separada y autenticada;
- límites de tamaño, timeouts y validación estricta de lat/lon/z/x/y;
- no permitir URLs arbitrarias desde parámetros, evitando SSRF;
- cabeceras de seguridad en la página y TLS obligatorio;
- logs estructurados sin tokens;
- backup de `current.json`, snapshots y crosswalk.

## 10. Fases de implementación

### Fase 0 — investigación y prueba de concepto

**Tamaño:** mediana.

Objetivos:

- confirmar geometría, licencia, semántica y compatibilidad real;
- reducir a cero las cuestiones que puedan invalidar la arquitectura.

Tareas:

- observar 14 días de respuestas y cabeceras;
- pedir confirmación/licencia al 112CV e ICV;
- descargar GPKG municipal y construir crosswalk revisado;
- disolver y comparar con mapa/PDF oficial;
- producir manualmente un GeoJSON y pocas teselas de prueba;
- crear/exportar `.osf` desde Android e iOS;
- probar expiración, alpha, sobrezoom, caché y fallos.

Entregables:

- informe de observación de cadencia;
- crosswalk de 542 municipios con revisión;
- geometría POC y diff visual;
- matriz de dispositivos completada;
- respuestas escritas sobre licencia/semántica o riesgos aceptados.

Dependencias: acceso a Android+iPhone físicos; fuente oficial disponible; contacto institucional.

Riesgos: no coincidencia municipal; iOS no conserva expiración OSF; permiso de reutilización no aclarado.

Criterios de aceptación:

- siete geometrías válidas, sin municipios sin asignar;
- coincidencia visual aceptada y discrepancias explicadas;
- capa visible y actualizable en ambos sistemas;
- no queda ninguna afirmación de circulación basada solo en nivel.

### Fase 1 — ingestión y normalización

**Tamaño:** mediana.

Objetivos: convertir fuentes inestables en un modelo interno probado.

Tareas:

- estructura TypeScript, adaptadores y esquemas Zod;
- recolector con cabeceras/hash/timeouts;
- fixtures y JSON Schemas;
- validaciones estructurales/semánticas;
- snapshot crudo y última válida;
- lógica current/forecast y códigos internos;
- reloj y política stale testeables.

Entregables: CLI `collect/validate/normalize`, snapshots normalizados y suite unitaria.

Dependencias: semántica de campos resuelta o documentada como desconocida.

Riesgos: cambio de esquema; timestamp ingenuo; discrepancia de situaciones.

Criterios: misma entrada produce mismo hash; payload inválido nunca cambia `current`; fallos conservan última válida.

### Fase 2 — geometrías y GeoJSON

**Tamaño:** mediana.

Objetivos: geometría reproducible y canónica.

Tareas:

- adaptador TypeScript para GPKG/WFS apoyado en `ogrinfo`/`ogr2ogr`;
- crosswalk versionado;
- validación y disolución;
- GPKG maestro, GeoJSON EPSG:4326 y simplificaciones;
- `/metadata`, `/zones.geojson`, zona individual y `/status`;
- pruebas de fronteras/enclaves.

Entregables: `zones.geojson`, versión geométrica, API espacial.

Dependencias: Fase 0 confirma modelo municipal.

Riesgos: topología, nombres, nuevos municipios.

Criterios: 542→7 sin pérdida; cobertura equivalente; puntos de prueba correctos; atribución incluida.

### Fase 3 — teselas XYZ

**Tamaño:** mediana.

Objetivos: overlay legible, accesible y cacheable.

Tareas:

- estilo SVG/Sharp y reglas z6–14;
- PNG32/metatiling y teselas transparentes;
- leyenda y stale overlay;
- precomputación solo en cambio semántico;
- ETag/caché y golden tests;
- medición de tamaño/tiempo.

Entregables: `/tiles`, `/legend.png`, informe de rendimiento.

Dependencias: Fase 2 y diseño visual aceptado.

Riesgos: demasiadas teselas, etiquetas cortadas, alpha inconsistente.

Criterios: caminos legibles; sin seams; render completo dentro del presupuesto acordado; colores/patrones validados. Si el candidato SVG/Sharp no los cumple, el adaptador de render se cambia sin alterar los contratos ni el resto del stack TypeScript.

### Fase 4 — configuración e importación en OsmAnd

**Tamaño:** pequeña-mediana.

Objetivos: instalación reproducible en ambos sistemas.

Tareas:

- generar `.osf` desde configuraciones exportadas reales;
- incluir icono, atribución, URLs y disclaimer;
- documentar Android/iOS con capturas;
- probar expiración, borrado, offline y actualización;
- publicar página de leyenda/metadatos.

Entregables: `previfoc.osf`, guía de instalación y matriz cerrada.

Dependencias: URL HTTPS estable y Fase 3.

Riesgos: diferencias de serialización, UI cambiante, caché persistente.

Criterios: instalación por una persona no técnica; cambio visible tras caducidad; no requiere editar archivos.

### Fase 5 — despliegue y monitorización

**Tamaño:** mediana.

Objetivos: servicio recuperable, auditable y observado.

Tareas:

- Docker; servicio web y cron;
- R2 versionado y puntero atómico;
- CDN, TLS, dominio y cabeceras;
- métricas, logs, alertas y monitor externo;
- backups, rollback, retención y runbook;
- CI/CD y escaneo de dependencias;
- simulacro de caída/cambio de esquema.

Entregables: entorno producción, dashboards/runbook, SLO inicial.

Dependencias: permiso de reutilización y dominio.

Riesgos: cron retrasado, caché vieja, credenciales, coste por teselas.

Criterios: rollback probado; alerta ante stale/esquema; recuperación sin perder última válida; canarios Android/iOS.

### Fase 6 — mejoras futuras

**Tamaño:** grande.

Posibles objetivos:

- adaptadores de resoluciones extraordinarias y cierres;
- visor web con polígonos pulsables;
- consulta/intersección de GPX o ruta y avisos por tramo;
- restricciones por actividad y espacio;
- OBF/SQLite offline versionado;
- historial y comparación temporal;
- WMS/WMTS para ecosistema GIS;
- PostGIS y colas al crecer el volumen;
- notificaciones con lenguaje jurídico revisado.

Criterio previo a avisos de ruta: cobertura oficial suficiente de restricciones, reglas por actividad, vigencia y pruebas de falsos negativos en fronteras.

## 11. Prueba de concepto de pocas horas

La POC valida la cadena, no crea el servicio completo.

1. Descargar los cuatro JSON con `curl`, guardando cabeceras y cuerpo.
2. Extraer las siete filas `z1`; resolver `nact` contra situaciones `ID_AVISO=3`.
3. Descargar GPKG `ICV.Municipios` desde el catálogo oficial.
4. Crear un crosswalk provisional por aliases; detenerse y revisar manualmente toda ambigüedad.
5. Unir `cod_ine_mun → idZonaPrevifoc` y disolver por zona.
6. Exportar `zones.geojson` con nivel, fuente y calidad.
7. Renderizar una imagen transparente y una pirámide reducida z6–10, suficiente para la primera prueba.
8. Servir temporalmente por HTTPS o túnel de pruebas con URL `{z}/{x}/{y}.png`.
9. Registrar la fuente mediante URL mágica o `.osf` de prueba en Android/iOS.
10. Comparar a la misma fecha con JPEG y PDF oficiales, prestando atención a 1N/1S, costa, enclaves y límites.
11. Modificar una copia controlada de una tesela, esperar expiración y verificar la nueva petición.

Pseudoflujo:

```text
fetch → validate → map municipality names to INE → dissolve →
join current situations → GeoJSON → transparent tiles → device test
```

Resultados que invalidan la POC:

- un municipio no puede asociarse sin conjetura;
- la geometría no coincide materialmente con la oficial;
- iOS no refresca la fuente remota después de la caducidad;
- el alpha oculta caminos a un nivel necesario;
- el permiso de reutilización es denegado.

## 12. Pruebas de aceptación globales

- fuente exacta, hora y recuperación visibles;
- diferencia clara entre actual y mañana;
- siete zonas y 542 municipios, sin duplicados ni pérdidas;
- traducción de los nueve códigos cubierta por tests;
- ningún texto “permitido/prohibido” derivado exclusivamente del nivel;
- datos stale visibles en API, leyenda y mapa;
- esquema roto no se publica;
- Android/iOS importan y actualizan la capa;
- caminos/nombres siguen siendo utilizables;
- atribución CC BY y aviso no oficial presentes;
- otro agente puede ejecutar cada fase usando estas decisiones sin escoger de nuevo formato, stack o política stale.

## 13. Riesgos priorizados

| Prioridad | Riesgo | Impacto | Mitigación |
|---:|---|---|---|
| P0 | Zonas no equivalen exactamente a municipios | Mapa incorrecto | Confirmación oficial + diff visual/topológico |
| P0 | Confundir riesgo con prohibición | Daño/asesoramiento falso | Modelo separado y revisión jurídica |
| P0 | Reutilización 112CV no autorizada/condicionada | Retirada del servicio | Consulta formal antes de producción |
| P1 | iOS no refresca igual que Android | Estado antiguo | Prueba física y parámetros exportados |
| P1 | Cambio silencioso de endpoint | Datos erróneos | Contratos, invariantes, última válida, alertas |
| P1 | Timestamp/zona horaria mal interpretado | Vigencia incorrecta | Confirmación y conservar raw |
| P1 | Caché de OsmAnd/CDN mantiene estado antiguo | Riesgo operativo | TTL, ETag, expiración, stale visible, pruebas |
| P2 | Crosswalk por nombres se rompe | Zona incompleta | Código INE persistente y revisión de diffs |
| P2 | Coste/volumen de teselas | Degradación | z6–14, solo cambios, CDN, métricas |
| P2 | Leyenda/fecha no siempre visibles | Mala interpretación | etiquetas overview + enlace + limitación documentada |

## 14. Preguntas abiertas priorizadas

1. **P0 — Polígonos:** ¿confirma 112CV/ICV que cada zona PREVIFOC es exactamente la unión de los municipios asignados por `idZonaPrevifoc`? ¿Existe una capa oficial directa no publicada?
2. **P0 — Semántica jurídica:** ¿qué restricciones generales siguen vigentes con nivel 3 según la normativa actual y qué fuente oficial publica cierres extraordinarios por territorio/actividad?
3. **P0 — Licencia:** ¿qué condiciones y atribución se aplican a los JSON, imágenes y PDF del 112CV? ¿Se permite cachear y redistribuir derivados?
4. **P1 — iOS:** ¿el `.osf` conserva URL, alpha, zoom y expiración de manera idéntica y refresca una tesela visible tras 15 minutos?
5. **P1 — Tiempo:** ¿`time` usa Europe/Madrid, representa publicación o vigencia, y existen `valid_from/valid_until` oficiales?
6. **P1 — Frecuencia:** ¿la publicación es diaria, puede corregirse intradía y existe una hora objetivo/SLA?
7. **P1 — Estabilidad:** ¿hay API documentada, versionada o contacto para avisos de cambio?
8. **P2 — Distribución:** ¿se acepta la limitación de leyenda/fecha no fija dentro de OsmAnd o se requiere otra experiencia complementaria?
9. **P2 — Circulación:** ¿qué actividades debe distinguir el producto: peatón, bicicleta, vehículo a motor, trabajo forestal, uso del fuego?
10. **P2 — Offline:** ¿el usuario necesita un paquete totalmente offline o basta la caché automática de XYZ?
11. **P3 — Actual/mañana:** ¿la capa de OsmAnd mostrará solo hoy y la previsión quedará en web/API, o se publicarán dos fuentes XYZ?

## 15. Fuentes citadas

- [112CV — Incendios forestales](https://www.112cv.gva.es/es/incendios-forestales)
- [Datos Abiertos — Municipios de la Comunitat Valenciana](https://dadesobertes.gva.es/es/dataset/delimitacion-territorial-municipios-de-la-comunitat-valenciana)
- [ICV WFS de delimitaciones](https://terramapas.icv.gva.es/0105_Delimitaciones?service=WFS&request=GetCapabilities)
- [ICV ArcGIS REST municipal](https://carto.icv.gva.es/arcgis/rest/services/0105_delimitaciones/0105_Delimitaciones/MapServer/0)
- [OsmAnd Raster Maps](https://osmand.net/docs/user/map/raster-maps)
- [OsmAnd Custom Package](https://osmand.net/docs/user/plugins/custom)
- [OsmAnd Import / Export](https://osmand.net/docs/user/personal/import-export)
- [DOGV — Decreto 91/2023](https://dogv.gva.es/datos/2023/07/07/pdf/2023_7436.pdf)
- [Cloudflare R2 public/custom domains](https://developers.cloudflare.com/r2/buckets/public-buckets/)
- [Cloudflare Workers Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/)
- [Render Cron Jobs](https://render.com/docs/cronjobs)
- [Railway Cron Jobs](https://docs.railway.com/cron-jobs)
- [Fly.io — Task scheduling](https://fly.io/docs/blueprints/task-scheduling/)
- [GitHub Actions scheduled events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [Fastify — TypeScript](https://fastify.dev/docs/latest/Reference/TypeScript/)
- [Zod](https://zod.dev/)
- [GDAL — ogr2ogr](https://gdal.org/en/stable/programs/ogr2ogr.html)
- [Turf — booleanPointInPolygon](https://turfjs.org/docs/api/booleanPointInPolygon)
- [Mapbox — geojson-vt](https://github.com/mapbox/geojson-vt)
- [Sharp — output PNG](https://sharp.pixelplumbing.com/api-output/)
