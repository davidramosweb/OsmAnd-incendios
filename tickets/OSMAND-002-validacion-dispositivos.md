# OSMAND-002 — Validar geometría y teselas en OsmAnd

**Estado:** completado con limitaciones aceptadas  
**Dependencias:** [OSMAND-001](./OSMAND-001-publicar-fuente-prueba.md)  
**Siguiente:** [WORKER-001](./WORKER-001-scaffold-cloudflare.md)

## Objetivo

Confirmar físicamente que la geometría y las teselas estáticas funcionan como overlay en OsmAnd Android e iOS antes de invertir trabajo en Cloudflare.

## Contexto

Este ticket es la barrera de salida del bloque geográfico. Los fallos visuales se corrigen en GEO/TILES, no en el Worker futuro.

Leer antes: [OSMAND_COMPATIBILITY.md](../OSMAND_COMPATIBILITY.md).

## Alcance

- Instalar la fuente temporal en un Android y un iPhone.
- Mantener el mapa vectorial de OsmAnd como mapa principal.
- Revisar z6–14, desplazamiento, sobrezoom y costa.
- Confirmar transparencia, bordes, legibilidad de caminos y ausencia de fondo blanco.
- Observar peticiones tras borrar caché y después de expirar una tesela.
- Documentar versión de OsmAnd, sistema operativo y diferencias entre plataformas.

## Fuera de alcance

- Estado dinámico.
- Cierre rojo real.
- `.osf` definitivo.
- Uso completamente offline.

## Entregables

- Matriz Android/iOS completada.
- Capturas en varios zooms.
- Registro de problemas y correcciones requeridas.
- Decisión explícita de aprobar o rechazar la barrera B.

## Criterios de aceptación

- [ ] La fuente se instala y activa en Android.
- [x] La fuente se instala y activa en iOS.
- [ ] Las siete zonas aparecen en la ubicación correcta.
- [ ] El mapa base, caminos y nombres permanecen legibles.
- [ ] No hay seams, halos, fondo opaco ni Y invertida.
- [ ] z6–14 funcionan y el sobrezoom posterior resulta aceptable.
- [ ] OsmAnd vuelve a solicitar una tesela tras la caducidad configurada.
- [ ] Cualquier diferencia entre Android e iOS queda documentada.

## Cierre de sesión

Solo marcar el ticket como terminado si la barrera B queda aprobada. WORKER-001 puede entonces tratar las plantillas como contrato inmutable.

## Avance y bloqueo de OSMAND-002 — 2026-07-18

La comprobación HTTP previa obligatoria se ejecutó contra la publicación HTTPS
antes de intentar cualquier validación de dispositivo:

```sh
.venv-geo/bin/python tools/osmand_http_check.py \
  https://mcp.davidramosweb.com/osmand-001 \
  --require-https --print-magic-url
```

El primer intento no tuvo resolución DNS dentro del sandbox. Repetido con
acceso de red autorizado, terminó con código 0 y pasó las nueve peticiones:
tesela cubierta z6, fallback z6, zoom inválido, cuatro coordenadas inválidas,
tesela cubierta z14 y espejo TMS. Se observaron los valores congelados:

- `6/31/24.png`: 200, `image/png`, 1.119 bytes y SHA-256
  `b063e13960a4ca08ada1f4b7b3569ed268b01089af1b4664ecbf15162cf1b72d`;
- `6/30/24.png`: 200 y los 201 bytes exactos de `transparent.png`;
- `14/8213/6173.png`: 200, 429 bytes y SHA-256
  `6011350e191e152adb3b2d63de6daeb7cd977b2742f39a54bc569d840b4dd44b`;
- `14/8213/10210.png`: 200 y fallback transparente, sin inversión TMS;
- PNG: `Cache-Control: private, max-age=300, must-revalidate`, CORS `*`;
- errores: 400/404 de texto plano con `Cache-Control: no-store`.

La URL mágica impresa coincide exactamente con la entrega de OSMAND-001.

### Compatibilidad oficial revisada

Se contrastó el procedimiento el 2026-07-18 con la documentación oficial
vigente de [Raster Maps](https://osmand.net/docs/user/map/raster-maps/) y
[Maps & Resources](https://osmand.net/docs/user/personal/maps-resources/).
La documentación confirma que:

- Android necesita habilitar Online Maps y en iOS los mapas ráster están
  disponibles por defecto;
- `{0}/{1}/{2}` equivale a `{z}/{x}/{y}` en ese orden;
- el alta manual admite Pseudo-Mercator, zoom mínimo/máximo, expiración en
  minutos y almacenamiento por imágenes individuales o SQLiteDB;
- como overlay, OsmAnd reescala la fuente fuera del rango configurado;
- al caducar, una tesela se vuelve a solicitar cuando se muestra;
- Android ofrece `Clear all tiles` y iOS `Clear cache` desde la ficha de la
  fuente.

### Evidencia de cliente disponible

Las sesiones de publicación `osmand-001-origin` y `osmand-001-tunnel` siguen
activas y no se reiniciaron ni cambiaron. El log temporal del origen contiene
268 GET con `User-Agent: OsmAndIOS_5.3.3`, todos con HTTP 200, entre
`2026-07-18T10:11:26Z` y `2026-07-18T10:19:04Z`:

| Zoom | Cubiertas | Fallback transparente | Total |
|---:|---:|---:|---:|
| 7 | 4 | 2 | 6 |
| 8 | 8 | 7 | 15 |
| 9 | 26 | 21 | 47 |
| 10 | 34 | 5 | 39 |
| 11 | 53 | 2 | 55 |
| 12 | 38 | 0 | 38 |
| 13 | 33 | 0 | 33 |
| 14 | 35 | 0 | 35 |
| **Total** | **231** | **37** | **268** |

Nueve coordenadas exactas reaparecen transcurridos entre 315 y 434 segundos;
por ejemplo, `11/1019/774` se solicitó de nuevo 434 segundos después. Esto es
coherente con la caducidad configurada de 300 segundos, pero el log por sí solo
no permite distinguir una recarga por expiración de un borrado de caché u otra
acción manual. No se observaron peticiones z6 ni existe evidencia visual o de
sobrezoom en el log.

El identificador permite registrar **OsmAnd iOS 5.3.3** como cliente observado,
pero por sí solo no aporta versión de iOS, modelo, método de alta o resultado
visual. El usuario confirmó después que la prueba se realizó en un iPhone
físico y que la fuente parece funcionar bien.

El usuario entregó además la captura
[`ios-overview-2026-07-18.jpg`](../data/osmand-002/evidence/ios-overview-2026-07-18.jpg),
conservada sin transformación con SHA-256
`267cc2b3b49ea6bf003cab1c6b767272825794895fb32e362bd53563c200bef8`.
La imagen es un JPEG RGB sRGB de 588 × 1280 px. El informe de evidencia y sus
límites están en [`data/osmand-002/REPORT.md`](../data/osmand-002/REPORT.md).

En la captura, la fuente está activa como overlay sobre el mapa vectorial. La
geometría ocupa la Comunitat Valenciana y sigue la costa en la posición
esperada; se ven los límites internos, la secuencia Castellón–Valencia–Alicante
y una orientación norte-sur correcta. El relleno es semitransparente y deja
legibles carreteras y nombres. No se aprecia fondo blanco, opacidad completa,
halo ni seam en esta vista general. Otros POI, avisos y trazados visibles no
pertenecen a PREVIFOC.

### Matriz de validación física

| Campo | Android | iOS |
|---|---|---|
| Dispositivo físico probado | No | Sí; confirmado explícitamente por el usuario |
| Sistema/modelo | Pendiente | Pendiente |
| Versión de OsmAnd | Pendiente | 5.3.3 observada en `User-Agent`; pendiente de confirmar en el dispositivo |
| Método de alta | Pendiente | Pendiente; no puede inferirse del log |
| Instalación y activación como overlay | Pendiente | Confirmada visualmente |
| Siete zonas y posición | Pendiente | Vista general coherente y límites internos visibles; falta detalle dirigido por zona |
| Transparencia, costa, seams, halos y fondo blanco | Pendiente | Correcto en vista general; falta revisión a máxima ampliación |
| Legibilidad de mapa base, caminos y nombres | Pendiente | Correcta en la captura general |
| z6–14 | Pendiente | Tráfico z7–14 observado; z6 y revisión visual pendientes |
| Sobrezoom posterior | Pendiente | Pendiente |
| Orientación XYZ | Pendiente visual; endpoint anti-TMS correcto | Correcta en vista general y endpoint anti-TMS correcto |
| Tras borrar caché | Pendiente | Pendiente; el log no identifica la acción que originó cada ráfaga |
| Tras expirar 5 minutos | Pendiente | Repeticiones compatibles, pero no causalmente acreditadas |
| Capturas | Pendiente | Una vista general recibida y archivada; faltan zooms dirigidos |

No se detectó un defecto HTTP ni una corrección técnica requerida. Los
resultados visuales no pueden darse por correctos o incorrectos sin observar
ambas aplicaciones físicas.

### Limitaciones y decisión sobre la barrera B

No hay `adb` disponible ni un Android conectado/autorizado. El iPhone fue
probado por el usuario fuera de una sesión dirigida; no está conectado ni hay
una sesión remota de OsmAnd que permita completar los controles pendientes.

El 2026-07-18 el usuario aprobó explícitamente cerrar esta etapa y continuar
con el ticket siguiente. **Barrera B: aprobada con limitaciones aceptadas por
el usuario.** No existe un rechazo técnico de GEO/TILES y OSMAND-002 deja de
bloquear WORKER-001.

La aprobación no convierte en realizadas las comprobaciones pendientes: no hay
prueba Android, y faltan modelo/versión de iOS, método de alta, zooms dirigidos,
sobrezoom y el ensayo controlado de caché. Las casillas de aceptación no
marcadas conservan esas desviaciones como riesgo conocido y no deben
reinterpretarse como evidencia que no se obtuvo.

Si se retoma la validación, el dato mínimo pendiente es una prueba dirigida en
un Android físico y, para el iPhone, modelo, versión de iOS y método de alta.
En ambos conviene capturar z6, z10, z14 y sobrezoom, además de una carga tras
borrar caché y otra después de más de 5 minutos.

TILES-002 se consumió exclusivamente en modo de solo lectura. No se modificaron,
regeneraron, sustituyeron, copiaron ni recolorearon sus teselas, manifiesto,
inventario, controles o PNG. Tampoco se modificaron GEO, TILES-001, la
publicación OSMAND-001 ni ninguna infraestructura, y no se implementaron Worker,
Cron, KV, caché persistente, recoloreado dinámico, `.osf` definitivo o página
pública completa.
