# Backlog del MVP PREVIFOC para OsmAnd

Este directorio divide el MVP en tickets ejecutables de forma aislada. Cada ticket está pensado para ocupar una sesión y contiene el contexto, alcance, dependencias, entregables y criterios de aceptación necesarios para trabajar sin reconstruir todo el razonamiento del proyecto.

## Decisiones globales fijadas

- El cliente objetivo es OsmAnd Android e iOS mediante teselas ráster XYZ.
- El MVP muestra únicamente el estado actual (`nact`), no la previsión de mañana.
- Las zonas son `1N`, `1S`, `2`, `3`, `4`, `5` y `6`, correspondientes a los IDs 53–59.
- La geometría se calcula una vez a partir de municipios oficiales y después queda congelada para el MVP.
- La capa usa relleno semitransparente y límites negros, sin etiquetas, rayos ni patrones.
- Colores: nivel 1 `#A4CC87`, nivel 2 `#FF9700`, nivel 3 `#E83D35`.
- Regla conservadora propia: nivel 3 implica que el servicio trata pistas y sendas forestales como cerradas al público.
- Nivel 1 o 2 no se rotula como “abierto”; solo significa que esta regla no determina un cierre.
- El servicio se identifica como independiente y no oficial.
- La actualización del estado se realiza cada hora.
- Si el estado oficial no corresponde al día actual en `Europe/Madrid`, las zonas se muestran grises.
- La primera arquitectura de despliegue es un único Cloudflare Worker con Static Assets, KV y Cron Trigger, sin R2 ni Cloudflare Images.
- El MVP se diseña para el nivel gratuito de Cloudflare y no debe superar 19.000 assets.

## Regla de trabajo por sesión

Al iniciar una sesión para un ticket:

1. leer este índice;
2. leer el ticket solicitado y únicamente sus dependencias directas si hace falta;
3. no ampliar el alcance con tareas de tickets posteriores;
4. registrar en el ticket cualquier desviación, decisión nueva o bloqueo;
5. verificar todos sus criterios de aceptación antes de declararlo terminado.

## Orden y dependencias

| Orden | Ticket | Resultado | Depende de |
|---:|---|---|---|
| 1 | [GEO-001](./GEO-001-obtener-fuentes-geograficas.md) | Fuentes geográficas reproducibles | — |
| 2 | [GEO-002](./GEO-002-crosswalk-municipal.md) | Correspondencia de 542 municipios | GEO-001 |
| 3 | [GEO-003](./GEO-003-disolver-validar-zonas.md) | Siete geometrías canónicas | GEO-002 |
| 4 | [GEO-004](./GEO-004-comparacion-visual.md) | Geometría aprobada contra mapa oficial | GEO-003 |
| 5 | [TILES-001](./TILES-001-formato-plantilla-indexada.md) | Contrato de PNG indexado probado | GEO-004 |
| 6 | [TILES-002](./TILES-002-generar-piramide-xyz.md) | Pirámide estática z6–14 | TILES-001 |
| 7 | [OSMAND-001](./OSMAND-001-publicar-fuente-prueba.md) | Fuente XYZ temporal instalable | TILES-002 |
| 8 | [OSMAND-002](./OSMAND-002-validacion-dispositivos.md) | Validación física Android/iOS | OSMAND-001 |
| 9 | [WORKER-001](./WORKER-001-scaffold-cloudflare.md) | Proyecto Cloudflare ejecutable | OSMAND-002 |
| 10 | [WORKER-002](./WORKER-002-ingesta-previfoc.md) | Estado actual validado | WORKER-001 |
| 11 | [WORKER-003](./WORKER-003-estado-kv.md) | Publicación horaria segura en KV | WORKER-002 |
| 12 | [WORKER-004](./WORKER-004-recoloreado-cache.md) | Teselas dinámicas coloreadas | WORKER-003 |
| 13 | [WEB-001](./WEB-001-pagina-informativa.md) | Página, leyenda y avisos | WORKER-004 |
| 14 | [OSMAND-003](./OSMAND-003-paquete-osf.md) | Instalador `.osf` definitivo | WEB-001 |
| 15 | [RELEASE-001](./RELEASE-001-despliegue-aceptacion.md) | MVP desplegado y aceptado | OSMAND-003 |

## Barreras de fase

### Barrera A — geometría

`GEO-004` debe aprobar las siete zonas antes de diseñar el formato definitivo de teselas.

### Barrera B — OsmAnd estático

`OSMAND-002` debe confirmar que las teselas se ven correctamente en Android e iOS antes de crear el Worker. Si falla, se corrige el bloque GEO/TILES; no se compensa el problema desde Cloudflare.

### Barrera C — publicación

`WORKER-004` debe demostrar recoloreado, obsolescencia y caché antes de crear el instalador definitivo y desplegar públicamente.

## Documentación de contexto

- [Fuentes y contratos](../DATA_SOURCES.md)
- [Compatibilidad OsmAnd](../OSMAND_COMPATIBILITY.md)
- [Arquitectura investigada](../ARCHITECTURE.md)
- [Plan técnico anterior](../PLAN.md)
- [Registro de decisiones](../DECISIONS.md)

Los documentos anteriores contienen investigación más amplia que el MVP. En caso de contradicción, prevalecen las decisiones globales de este índice y el alcance explícito del ticket activo.
