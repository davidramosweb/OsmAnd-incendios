# Registro de decisiones propuestas

Estas decisiones son propuestas de arquitectura para el MVP. Se convierten en definitivas cuando se cierren las preguntas P0 de `PLAN.md` y la Fase 0 cumpla sus criterios de aceptación.

## ADR-001 — Usar arquitectura híbrida XYZ + GeoJSON + API

- **Estado:** propuesta recomendada.
- **Contexto:** OsmAnd Android/iOS consume bien teselas ráster, pero el proyecto necesita conservar geometría, propiedades e interacción futura.
- **Decisión:** publicar XYZ como capa móvil, GeoJSON como contrato vectorial, `/status` como consulta puntual y `.osf` como instalador.
- **Consecuencias positivas:** compatibilidad cruzada, CDN eficiente, independencia de OsmAnd y base para rutas.
- **Consecuencias negativas:** varios artefactos deben versionarse y probarse juntos; la interacción no ocurre al tocar el ráster.
- **Alternativas descartadas:** solo GeoJSON no tiene soporte dinámico documentado en OsmAnd; solo WMS/WMTS no resuelve el cliente; solo descargable no mantiene actualidad.

## ADR-002 — Reconstruir zonas disolviendo municipios oficiales

- **Estado:** condicionada a confirmación/POC.
- **Contexto:** los endpoints PREVIFOC carecen de geometría; `municipios` asigna los 542 municipios a siete zonas y el ICV publica límites oficiales.
- **Decisión:** crear una tabla revisada de correspondencia a código INE y disolver `ICV.Municipios` por `idZonaPrevifoc`.
- **Calidad publicada:** `derived_from_official_municipal_boundaries`, no `official_previfoc_polygon`.
- **Consecuencias positivas:** precisión, trazabilidad, licencia CC BY 4.0, mantenimiento reproducible.
- **Consecuencias negativas:** el vínculo por nombre exige revisión; la equivalencia de límites es una inferencia hasta que la autoridad la confirme.
- **Alternativas descartadas:** digitalizar el PNG/JPEG, por baja precisión y porque existe cartografía oficial; usar comarcas, porque las zonas no coinciden con ese catálogo.
- **Reversibilidad:** alta; si aparece una capa PREVIFOC oficial, sustituir el adaptador geométrico conservando el modelo.

## ADR-003 — No inferir circulación desde el nivel PREVIFOC

- **Estado:** obligatoria por seguridad.
- **Contexto:** nivel 3 significa riesgo extremo y puede activar reglas concretas, pero una prohibición de acceso depende de norma, resolución, actividad, lugar y vigencia.
- **Decisión:** separar `risk_level` de `circulation_status`. Sin evidencia oficial aplicable, usar `not_determined`.
- **Consecuencias positivas:** evita falsas afirmaciones de vía abierta/cerrada; permite añadir restricciones con procedencia.
- **Consecuencias negativas:** el MVP no puede cumplir literalmente “circulación permitida” para todas las zonas; expone honestamente la falta de datos.
- **Alternativa descartada:** `nivel 1=permitido`, `nivel 2=precaución`, `nivel 3=prohibido`; jurídicamente insostenible y contraria al encargo.

## ADR-004 — XYZ estándar, PNG transparente, z6–14

- **Estado:** propuesta para validar en dispositivos.
- **Contexto:** el mapa debe preservar caminos y funcionar en ambas plataformas.
- **Decisión:** EPSG:3857, XYZ con Y no invertida, PNG32 256 px, zoom 6–14, fill alpha bajo y sobrezoom posterior.
- **Consecuencias positivas:** máxima compatibilidad, canal alpha fiable, configuración simple y volumen acotado.
- **Consecuencias negativas:** no hay interacción; a zoom muy alto el borde se sobreescala; PNG pesa más que WebP.
- **Alternativas descartadas:** WebP hasta probar decodificación en todas las versiones; z15+ por volumen y poco beneficio en límites de zonas; TMS por complejidad innecesaria.

## ADR-005 — Instalar mediante `.osf` y actualizar mediante la URL remota

- **Estado:** propuesta para Fase 0.
- **Contexto:** escribir manualmente URL, zoom y expiración crea errores y dificulta atribución.
- **Decisión:** distribuir un `.osf` con `MAP_SOURCES`, icono, atribución, enlaces y disclaimer. El estado diario no se incrusta; llega por XYZ estable.
- **Consecuencias positivas:** una instalación manual y actualizaciones posteriores transparentes al visualizar.
- **Consecuencias negativas:** el OSF no se autoactualiza y hay diferencias de implementación por verificar.
- **Alternativas:** URL mágica solo para POC; pasos manuales como fallback documentado.

## ADR-006 — TypeScript y Fastify como stack principal

- **Estado:** propuesta recomendada.
- **Contexto:** la mayor parte del sistema es ingesta HTTP, validación, dominio, generación de artefactos y API. La geometría pesada se procesa al construir una versión, mientras el runtime consulta solo siete zonas.
- **Decisión:** TypeScript sobre Node.js LTS, Zod, Fastify y `fetch` nativo. GDAL/OGR se invoca como herramienta externa para GPKG/WFS, topología, disolución y reproyección; Turf cubre operaciones GeoJSON ligeras.
- **Consecuencias positivas:** un solo lenguaje de aplicación, tipos compartidos de extremo a extremo, menor cambio de contexto y frontera GIS explícita y reemplazable.
- **Consecuencias negativas:** GDAL sigue requiriendo una imagen Docker cuidada; algunas operaciones se realizan fuera del proceso Node y necesitan manejo estricto de errores, timeouts y argumentos.
- **Alternativas descartadas:** Python/FastAPI como stack completo, porque obligaría a mantener otro lenguaje sin que el runtime lo necesite; reemplazar GDAL por implementaciones TypeScript propias, porque aumenta el riesgo topológico.

## ADR-007 — No usar PostGIS en el MVP

- **Estado:** propuesta recomendada.
- **Contexto:** siete zonas, 542 polígonos fuente y un snapshot diario no justifican una base espacial operada.
- **Decisión:** GPKG como maestro geométrico, JSON/GeoJSON como salida y almacenamiento de objetos versionado. Para `/status`, un prefiltro bbox y Turf recorren los siete MultiPolygon en memoria.
- **Consecuencias positivas:** menos coste y fallos, backup simple, reproducibilidad.
- **Consecuencias negativas:** consultas históricas/rutas masivas no escalan igual.
- **Umbral de revisión:** restricciones granulares, concurrencia de edición, miles de objetos o consultas de ruta sostenidas.

## ADR-008 — Precomputar teselas solo ante cambio semántico

- **Estado:** propuesta recomendada.
- **Contexto:** la geometría casi no cambia y PREVIFOC parece diario; renderizar cada 15 minutos desperdiciaría recursos.
- **Decisión:** el sondeo frecuente calcula hash; generar nueva pirámide solo si cambia estado, vigencia, stale o geometría.
- **Consecuencias positivas:** coste predecible, objetos inmutables y rollback.
- **Consecuencias negativas:** cambio de stale también requiere artefactos visuales; hay que distinguir hash crudo y semántico.
- **Alternativa descartada:** render on-demand como única vía, porque introduce latencia y cold starts en OsmAnd.

## ADR-009 — Publicación versionada con puntero atómico

- **Estado:** obligatoria para producción.
- **Contexto:** sobrescribir miles de rutas “current” puede mezclar colores de dos snapshots.
- **Decisión:** escribir `artifacts/{snapshot_id}`, verificar, y después cambiar `current.json`. La API Fastify resuelve rutas estables contra el puntero.
- **Consecuencias positivas:** coherencia, rollback de un objeto, artefactos auditables.
- **Consecuencias negativas:** el servidor debe hacer la resolución; la CDN necesita TTL/purge correcto.
- **Alternativa descartada:** copiar directamente sobre `/tiles/current`; ventana de publicación parcial.

## ADR-010 — Mantener última versión válida y marcar stale

- **Estado:** obligatoria.
- **Contexto:** una fuente de seguridad puede caer; borrar la capa o conservarla sin aviso son comportamientos peligrosos.
- **Decisión:** conservar la última versión validada. Tras vencer, API, leyenda y teselas indican obsolescencia. No promover automáticamente la previsión previa.
- **Consecuencias positivas:** continuidad con honestidad; evita datos vacíos interpretados como riesgo bajo.
- **Consecuencias negativas:** exige render de estado stale y lenguaje claro.
- **Alternativas descartadas:** servir vacío, mantener colores sin marca, o inventar vigencia.

## ADR-011 — Evaluar SVG por metatiles y Sharp como renderizador TypeScript

- **Estado:** propuesta para benchmark en Fase 3.
- **Contexto:** se requieren alpha, bordes/patrones, reglas por zoom, etiquetas y ausencia de seams.
- **Decisión:** generar SVG por metatiles desde geometría proyectada/recortada y rasterizar a PNG32 con Sharp. Usar buffer y recorte para bordes, anclas de etiqueta versionadas y golden tests; `geojson-vt` queda como candidato para indexado, simplificación y clipping.
- **Consecuencias positivas:** implementación y pruebas en TypeScript, estilos declarativos sencillos y Sharp/libvips con buen soporte de SVG, alpha y PNG.
- **Consecuencias negativas:** se asume más lógica cartográfica propia; seams, patrones y etiquetas deben probarse de forma explícita; Sharp añade una dependencia nativa.
- **Plan de contingencia:** si el benchmark falla en calidad, determinismo o tiempo, sustituir únicamente el adaptador de render por un motor dedicado en Docker, manteniendo contratos, golden tests y el resto del sistema TypeScript.
- **Alternativas descartadas:** render on-demand como única vía por latencia; TileServer GL/MapLibre por añadir pipeline vector tile + GL; GeoServer por sobrecarga; Tippecanoe solo porque no produce el PNG final.

## ADR-012 — Usar Render + R2 + CDN para el primer despliegue

- **Estado:** propuesta, dependiente de cuentas/presupuesto.
- **Contexto:** se necesita un contenedor web, un cron y almacenamiento duradero de objetos.
- **Decisión:** misma imagen en Render Web Service y Cron Job; R2 privado; Cloudflare delante del dominio.
- **Consecuencias positivas:** baja complejidad, cron con una ejecución activa, portabilidad S3/Docker.
- **Consecuencias negativas:** dos proveedores; el almacenamiento local de Render es efímero; caché debe configurarse.
- **Alternativas:** Railway comparable, pero sus cron pueden variar y saltan si el anterior sigue activo; Fly.io requiere más configuración de cron; AWS es robusto pero excesivo para el MVP; GitHub Actions se reserva para CI/POC porque los schedules pueden retrasarse o descartarse.

## ADR-013 — No publicar WMS/WMTS en el MVP

- **Estado:** propuesta recomendada.
- **Contexto:** estándares útiles para GIS pero no mejoran la ruta principal de OsmAnd.
- **Decisión:** API/GeoJSON/XYZ primero. Evaluar WMS/WMTS en Fase 6 si hay consumidores reales.
- **Consecuencias positivas:** menos servicios y superficie de fallo.
- **Consecuencias negativas:** usuarios GIS deben usar GeoJSON/XYZ inicialmente.
- **Alternativa descartada:** GeoServer de inicio, porque añade operación sin resolver el requisito móvil.

## ADR-014 — Separar estado actual y previsión

- **Estado:** obligatoria.
- **Contexto:** `nact` y `npre` son periodos distintos, pero comparten zona.
- **Decisión:** dos registros/objetos por zona o una estructura con periodos explícitos; las teselas por defecto muestran solo `current`.
- **Consecuencias positivas:** evita mostrar mañana como vigente; contrato extensible.
- **Consecuencias negativas:** si se desea visualizar mañana en OsmAnd se necesita una segunda fuente/URL.
- **Resolución:** el `.osf` 2.0 registra `PREVIFOC — Hoy` y `PREVIFOC — Mañana`; la previsión usa trama diagonal y no confirma cierres futuros.

## ADR-015 — Conservar procedencia y valores originales

- **Estado:** obligatoria.
- **Contexto:** los endpoints carecen de contrato y algunos timestamps/campos son ambiguos.
- **Decisión:** guardar cuerpo, cabeceras, URL, hash, recuperación y `time` raw; toda transformación declara si es verificada o derivada.
- **Consecuencias positivas:** auditoría, depuración y posibilidad de reinterpretar sin perder evidencia.
- **Consecuencias negativas:** almacenamiento e implicaciones de licencia/retención que hay que acordar.

## Decisiones aplazadas

| Tema | Motivo | Momento de decisión |
|---|---|---|
| Fuente de restricciones extraordinarias | No se encontró un feed oficial estructurado | Tras consulta jurídica/institucional |
| WMS/WMTS público | Sin consumidor MVP | Fase 6 |
| PostGIS | Volumen insuficiente | Al añadir rutas/restricciones granulares |
| OBF y paquete offline | Actualización manual peligrosa para estado diario | Tras validar necesidad real offline |
| Visor MapLibre | No necesario para OsmAnd | Cuando se priorice interacción web |
| Segundo overlay “mañana” | Puede confundir y duplica fuente | Fase 4 con pruebas de UX |
| Valor exacto de caducidad/stale | Falta observar la cadencia real | Final de Fase 0 |
| Texto legal definitivo | Requiere revisión y permiso | Antes de producción pública |

## Decisiones que requieren aprobación explícita

1. Aceptar que el MVP no afirma apertura/cierre sin otra fuente oficial.
2. Aceptar la limitación de no tener leyenda/fecha fija en la pantalla de OsmAnd.
3. Aceptar geometría derivada municipal si la validación coincide pero no llega confirmación formal.
4. Elegir proveedor y presupuesto de producción.
5. Definir periodo de retención de snapshots crudos conforme a licencia.
