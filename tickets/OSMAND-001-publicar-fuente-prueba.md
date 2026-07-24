# OSMAND-001 — Publicar una fuente XYZ estática de prueba

**Estado:** completado  
**Dependencias:** [TILES-002](./TILES-002-generar-piramide-xyz.md)  
**Siguiente:** [OSMAND-002](./OSMAND-002-validacion-dispositivos.md)

## Objetivo

Servir temporalmente la pirámide estática mediante HTTPS e instalarla como overlay en OsmAnd sin desarrollar todavía el Worker definitivo.

## Contexto

Esta prueba aísla la compatibilidad de OsmAnd. Todas las zonas pueden usar colores fijos de prueba; no se requiere actualización horaria ni KV.

## Alcance

- Publicar las teselas en una URL temporal `{z}/{x}/{y}.png`.
- Configurar `Content-Type: image/png`, CORS público y caché corta de prueba.
- Servir la tesela transparente con HTTP 200 cuando la coordenada válida no tenga plantilla.
- Crear una URL mágica o configuración manual mínima para instalar la fuente.
- Documentar pasos exactos de activación como overlay.
- Registrar peticiones y errores suficientes para la sesión de validación.

## Fuera de alcance

- `.osf` definitivo.
- Cron, KV o recoloreado dinámico.
- Página pública completa.

## Entregables

- URL HTTPS temporal y estable durante OSMAND-002.
- Configuración de instalación de prueba.
- Guía breve para Android e iOS.
- Comprobación HTTP automatizada de varias teselas.

## Criterios de aceptación

- [x] Una tesela conocida responde 200 y `image/png`.
- [x] Una tesela válida fuera de cobertura responde con PNG transparente.
- [x] Coordenadas o zoom inválidos responden 400/404 sin HTML ambiguo.
- [x] La fuente puede registrarse al menos en un dispositivo antes de cerrar el ticket.
- [x] La URL conserva XYZ sin invertir Y.

## Cierre de sesión

Entregar a OSMAND-002 la URL, el procedimiento de instalación y una lista de coordenadas de prueba por zoom.

## Avance verificable de OSMAND-001 — 2026-07-18

La implementación y publicación HTTPS están terminadas y permanecen
estrictamente dentro de OSMAND-001. No se cierra el ticket ni se entrega todavía
a OSMAND-002 porque falta confirmar el alta en un dispositivo físico.

### URL y publicación

- URL HTTPS base final: `https://mcp.davidramosweb.com/osmand-001`.
- Patrón final:
  `https://mcp.davidramosweb.com/osmand-001/tiles/{z}/{x}/{y}.png`.
- Origen reproducible: `tools/osmand_xyz_server.py`, en
  `http://127.0.0.1:8765` detrás de un frontal HTTPS.
- Configuración activa: `deploy/osmand-001/cloudflared.active.yml`. Solo la
  ruta `/osmand-001/tiles/*` llega a OSMAND-001; el resto del hostname conserva
  el destino MCP anterior.
- Origen y túnel permanecen activos en las sesiones `screen`
  `osmand-001-origin` y `osmand-001-tunnel`, con cuatro conexiones QUIC.
- Limitación operativa: la máquina debe permanecer encendida. Tras un reinicio
  hay que recrear las dos sesiones con los comandos documentados.

### HTTP, caché, CORS y fallback

- Caché temporal: `Cache-Control: private, max-age=300, must-revalidate` (5 min).
  `private` conserva el TTL corto frente al mínimo general de cuatro horas de
  Cloudflare y evita caché CDN compartida; CORS continúa siendo público.
- CORS: `Access-Control-Allow-Origin: *`; `GET`, `HEAD` y `OPTIONS`.
- Fallback: toda coordenada XYZ válida z6–14 ausente en el inventario recibe
  HTTP 200 y los 201 bytes exactos de `data/tiles-002/transparent.png`.
- Zoom fuera de 6–14: HTTP 404 de texto plano. Enteros inválidos, negativos o
  fuera de `0..2^z-1`: HTTP 400 de texto plano. Los errores usan `no-store` y
  nunca HTML.
- Teselas cubiertas: lectura directa y comprobación SHA-256 en cada respuesta;
  no hay transformación de `PLTE`, `tRNS`, `IDAT`, color, índice o ruta.
- Registro mínimo: JSONL a stdout con hora UTC, método, ruta, status, resultado,
  XYZ, bytes, latencia, IP, User-Agent y request ID; sin cuerpos, query strings,
  plataforma de observabilidad ni almacenamiento persistente.

### Coordenadas de prueba por zoom

| Zoom | XYZ cubierta |
|---:|---:|
| 6 | `31/24` |
| 7 | `63/48` |
| 8 | `126/96` |
| 9 | `253/193` |
| 10 | `507/387` |
| 11 | `1015/774` |
| 12 | `2030/1557` |
| 13 | `4061/3114` |
| 14 | `8213/6173` |

Controles específicos automatizados: cubierta `6/31/24`, exterior válida
`6/30/24`, zoom inválido `5/31/24`, x/y no enteros, negativos y fuera de
rango, cubierta alta `14/8213/6173` y espejo TMS `14/8213/10210`.

### Integridad comprobada antes de publicar

Pasaron las seis barreras exigidas:

```sh
.venv-geo/bin/python tools/geo_sources.py validate
.venv-geo/bin/python tools/geo_crosswalk.py validate
.venv-geo/bin/python tools/geo_zones.py validate
.venv-geo/bin/python tools/geo_compare.py validate
.venv-geo/bin/python tools/tile_template.py validate
.venv-geo/bin/python tools/tile_pyramid.py validate
```

La última regeneró temporalmente y comparó 9.515 archivos, 9.507 teselas y 17
parejas de continuidad byte a byte. Hashes directos observados:

- `zones.gpkg`: `e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0`;
- `zones.geojson`: `b76ffaeec4eb9c75ee23991ed9386136d74d94a5bc2603700d65b37e6fb528c2`;
- `crosswalk.csv`: `0ca0ed22ccaaa6994d4701bd75da1d1355fcb945f4e7dfaf1b22472743294876`;
- `transparent.png`: `00af44e300322d960f89aaa5dac93b0517fd1625ec0c058f3212661276a0d0ba`;
- `tiles.sha256`: `4fd05f73854d7cb620aa1d2721096b54dd1217f29c514f3242448febdb9f1bc0`;
- `manifest.json`: `5534833f228772b4e25602420cdc51024603b6971d8a58c5ab590649dd8a1972`.

### Resultados HTTP locales y HTTPS

`tests.test_osmand_xyz_server` pasa 5/5. La matriz extremo a extremo comprueba:

| Petición | Resultado local esperado y observado |
|---|---|
| `6/31/24.png` | 200, `image/png`, CORS `*`, caché 300 s, bytes exactos |
| `6/30/24.png` | 200, `image/png`, bytes exactos de `transparent.png` |
| z5 | 404, texto plano, `no-store` |
| x/y no enteros, negativos o fuera del mundo | 400, texto plano, `no-store` |
| `14/8213/6173.png` | 200, bytes exactos de la tesela cubierta |
| `14/8213/10210.png` | 200, fallback transparente; no hay inversión TMS |

Resultados de la ejecución CLI local: `6/31/24.png` devolvió 1.119 bytes con
SHA-256 `b063e13960a4ca08ada1f4b7b3569ed268b01089af1b4664ecbf15162cf1b72d`;
`14/8213/6173.png`, 429 bytes con SHA-256
`6011350e191e152adb3b2d63de6daeb7cd977b2742f39a54bc569d840b4dd44b`;
ambos fallbacks devolvieron exactamente 201 bytes y SHA-256
`00af44e300322d960f89aaa5dac93b0517fd1625ec0c058f3212661276a0d0ba`.
La suite completa del repositorio pasa 52/52.

El sandbox ordinario no permite abrir un socket local; repetidas las pruebas
con permiso explícito para `127.0.0.1`, todas pasan. La misma matriz contra
`https://mcp.davidramosweb.com/osmand-001` con `--require-https` pasa completa:
status, MIME, CORS, caché, longitud y SHA-256 coinciden en las nueve peticiones.
Cloudflare devuelve `CF-Cache-Status: BYPASS` para las respuestas privadas.

### Instalación Android/iOS y límites

`deploy/osmand-001/README.md` contiene la URL mágica parametrizada, alta manual,
activación como overlay, caducidad de 5 minutos y borrado de caché para Android
e iOS. La URL mágica usa `{0}/{1}/{2}` en orden XYZ y zoom 6–14. No se ha creado
un `.osf`, conforme al alcance.

URL mágica final:

```text
https://osmand.net/add-tile-source?name=PREVIFOC%20prueba%20temporal&min_zoom=6&max_zoom=14&url_template=https%3A%2F%2Fmcp.davidramosweb.com%2Fosmand-001%2Ftiles%2F%7B0%7D%2F%7B1%7D%2F%7B2%7D.png
```

Limitaciones abiertas: los nombres exactos de la UI pueden variar con la versión
de tienda. La versión de OsmAnd y el modelo de dispositivo no se comunicaron.

## Cierre de OSMAND-001 — 2026-07-18

El usuario confirmó que la fuente funciona en OsmAnd. Esta confirmación cumple
el criterio físico mínimo de registro y visualización como overlay, por lo que
OSMAND-001 queda cerrado. La matriz exhaustiva Android/iOS, comportamiento de
caché en dispositivo, descarga sin conexión y captura de versiones pertenece a
OSMAND-002 y no se ha iniciado en esta sesión.

Entrega exacta a OSMAND-002:

- base HTTPS: `https://mcp.davidramosweb.com/osmand-001`;
- plantilla: `https://mcp.davidramosweb.com/osmand-001/tiles/{z}/{x}/{y}.png`;
- URL mágica final registrada arriba;
- caché: `private, max-age=300, must-revalidate`; CORS: `*`;
- fallback: `transparent.png` exacto para XYZ válido sin cobertura;
- pruebas y coordenadas por zoom: secciones anteriores de este ticket;
- procesos activos: sesiones `screen` `osmand-001-origin` y
  `osmand-001-tunnel`; la máquina debe permanecer encendida.

TILES-002, TILES-001 y todas las entradas GEO se consumieron en modo de solo
lectura y no se modificaron, regeneraron, sustituyeron ni recolorearon. No se
inició OSMAND-002 ni se implementaron Worker, Cron, KV, caché persistente,
recoloreado dinámico, `.osf` definitivo o página pública completa.
