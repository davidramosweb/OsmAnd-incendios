# OSMAND-001 — Publicación temporal XYZ

Esta configuración publica, sin transformar, la entrada congelada
`data/tiles-002/`. Es temporal para la validación posterior en dispositivos y
no contiene Worker, Cron, KV, caché persistente, recoloreado ni una página web.

## Contrato HTTP

- URL final de tesela:
  `https://mcp.davidramosweb.com/osmand-001/tiles/{z}/{x}/{y}.png`.
- Zoom: 6–14; Y es XYZ y crece hacia el sur, nunca TMS.
- Tesela cubierta: bytes exactos de `data/tiles-002/{z}/{x}/{y}.png`.
- Coordenada XYZ válida sin plantilla: HTTP 200 con los 201 bytes exactos de
  `data/tiles-002/transparent.png`.
- Zoom no disponible: HTTP 404 de texto plano.
- Coordenada no entera, negativa o fuera de `0..2^z-1`: HTTP 400 de texto plano.
- PNG: `Content-Type: image/png`, `Access-Control-Allow-Origin: *` y
  `Cache-Control: private, max-age=300, must-revalidate`.
- Error: `Content-Type: text/plain; charset=utf-8` y `Cache-Control: no-store`;
  nunca una página HTML generada por el servidor.

Cinco minutos es una caché privada del cliente, deliberadamente corta y
temporal. `private` evita que el Browser Cache TTL general de Cloudflare eleve
el valor a cuatro horas y que el CDN compartido almacene las teselas. No es la
política del servicio final.

## Validar y arrancar el origen de solo lectura

Desde la raíz del proyecto:

```sh
.venv-geo/bin/python tools/osmand_xyz_server.py validate
.venv-geo/bin/python tools/osmand_xyz_server.py serve --host 127.0.0.1 --port 8765
```

El arranque calcula los hashes de las 9.507 teselas, exige el inventario y los
metadatos congelados y rechaza enlaces simbólicos o rutas adicionales. Cada
tesela cubierta vuelve a comprobar su hash al responder. El proceso solo lee
TILES-002.

## Publicar por HTTPS con el túnel autorizado

`cloudflared.active.yml` añade al túnel existente exclusivamente la ruta
`/osmand-001/tiles/* → http://127.0.0.1:8765`. El resto de
`mcp.davidramosweb.com` conserva su destino anterior `http://localhost`. Este
túnel no es un Cloudflare Worker y no almacena ni modifica teselas.

Origen y túnel se mantienen en sesiones `screen` desacopladas:

```sh
screen -dmS osmand-001-origin /bin/zsh -c \
  "exec '.venv-geo/bin/python' 'tools/osmand_xyz_server.py' serve \
  --host 127.0.0.1 --port 8765 >> /tmp/osmand-001-origin.jsonl \
  2>> /tmp/osmand-001-origin.err"

screen -dmS osmand-001-tunnel /bin/zsh -c \
  "exec /opt/homebrew/bin/cloudflared tunnel \
  --config 'deploy/osmand-001/cloudflared.active.yml' \
  run OSMAND_TUNNEL_ID \
  >> /tmp/osmand-001-cloudflared.log \
  2>> /tmp/osmand-001-cloudflared.err"

screen -ls
```

Los logs temporales son `/tmp/osmand-001-origin.jsonl`,
`/tmp/osmand-001-origin.err`, `/tmp/osmand-001-cloudflared.log` y
`/tmp/osmand-001-cloudflared.err`. Para detener la publicación:

```sh
screen -S osmand-001-origin -X quit
screen -S osmand-001-tunnel -X quit
```

No se usan LaunchAgents: macOS bloquea a procesos de segundo plano el acceso a
este proyecto dentro de `Documents`. Copiar la pirámide a otra ubicación para
evitarlo contradiría la obligación de consumir exactamente `data/tiles-002/`.
La URL permanece disponible mientras esta máquina siga encendida; tras un
reinicio hay que volver a arrancar origen y túnel con los comandos documentados.

## Comprobación HTTP final

Primero puede ejecutarse contra localhost y, después, obligando HTTPS contra la
URL publicada:

```sh
.venv-geo/bin/python tools/osmand_http_check.py http://127.0.0.1:8765
.venv-geo/bin/python tools/osmand_http_check.py \
  https://mcp.davidramosweb.com/osmand-001 \
  --require-https --print-magic-url
```

La comprobación solicita una tesela z6 cubierta, el fallback z6, zoom z5,
cuatro variantes x/y inválidas, una tesela z14 cubierta y su coordenada espejo
TMS. Exige status, tipo MIME, CORS, caché, firma, longitud y bytes exactos. La
tesela z14 `8213/6173` debe tener contenido y `8213/10210` debe ser el fallback;
así se detecta una inversión de Y en el endpoint.

Coordenadas cubiertas de diagnóstico, una por zoom:

| z | x | y |
|---:|---:|---:|
| 6 | 31 | 24 |
| 7 | 63 | 48 |
| 8 | 126 | 96 |
| 9 | 253 | 193 |
| 10 | 507 | 387 |
| 11 | 1015 | 774 |
| 12 | 2030 | 1557 |
| 13 | 4061 | 3114 |
| 14 | 8213 | 6173 |

## Registrar la fuente en OsmAnd

El verificador imprime la URL mágica exacta al añadir `--print-magic-url`. Su
forma es:

```text
https://osmand.net/add-tile-source?name=PREVIFOC%20prueba%20temporal&min_zoom=6&max_zoom=14&url_template=https%3A%2F%2Fmcp.davidramosweb.com%2Fosmand-001%2Ftiles%2F%7B0%7D%2F%7B1%7D%2F%7B2%7D.png
```

La URL mágica registra la fuente, pero la caducidad se ajusta manualmente a
cinco minutos porque ese parámetro no forma parte del enlace documentado.

### Android

1. En OsmAnd, ir a `Menú → Complementos → Mapas en línea → ⋮ → Activar`.
2. Abrir la URL mágica en el dispositivo y elegir OsmAnd.
3. Ir a `Menú → Configurar mapa → Mapa superpuesto` y seleccionar
   `PREVIFOC prueba temporal`; conservar el mapa vectorial como principal.
4. Ir a `Menú → Mapas y recursos → Local → Fuentes de mapas`, abrir el menú de
   la fuente, elegir `Editar` y fijar `Tiempo de caducidad` en 5 minutos.
5. Centrar el mapa en la Comunitat Valenciana, comprobar z6 y z14 y, si se
   necesita repetir sin caché, usar `Borrar todas las teselas` en ese mismo menú.

Alternativa manual: `Menú → Configurar mapa → Fuente del mapa → Añadir
manualmente`; nombre `PREVIFOC prueba temporal`, URL
`https://mcp.davidramosweb.com/osmand-001/tiles/{z}/{x}/{y}.png`, zoom 6–14,
Pseudo-Mercator, caducidad 5
minutos y almacenamiento por imágenes individuales.

### iOS

1. Abrir la URL mágica en Safari y elegir OsmAnd; los mapas ráster están
   habilitados por defecto en iOS.
2. Ir a `Menú → Configurar mapa → Overlay / Underlay → Overlay`, activar la
   capa y elegir `PREVIFOC prueba temporal`.
3. Mantener el mapa vectorial como mapa principal y activar `Mostrar símbolos
   del mapa` para conservar nombres y caminos visibles.
4. Ir a `Menú → Mapas y recursos → Local → Mapas ráster en línea → ⓘ → Editar`
   y fijar la caducidad en 5 minutos.
5. Comprobar z6 y z14. Para repetir sin caché, usar `Borrar caché` desde la
   ficha de la fuente.

Alternativa manual: desde `Overlay / Underlay`, pulsar `Añadir fuente en línea`
y usar el mismo nombre, URL, zoom 6–14, Pseudo-Mercator y caducidad de 5 minutos.

Los nombres exactos de algunos controles pueden variar con el idioma y versión
de tienda. Las capturas, versiones y observación física pertenecen a la sesión
de dispositivo; OSMAND-001 solo deja preparado el procedimiento instalable.

## Registro mínimo para la prueba

Cada petición produce una línea JSON en stdout con UTC, método, ruta, status,
resultado (`covered_tile`, `transparent_fallback` o error), XYZ, bytes, tiempo,
IP del cliente o `X-Forwarded-For`, `User-Agent`, política de caché y un
`request_id`. No se registran cuerpos ni query strings y no se crea un sistema
de observabilidad o retención persistente. El operador puede conservar stdout
solo durante la sesión de validación.

## Limitación pendiente

La URL está publicada y las comprobaciones HTTPS pasan. OSMAND-001 solo queda
pendiente de abrir la URL mágica en un Android o iPhone físico y confirmar que
`PREVIFOC prueba temporal` aparece seleccionable como overlay. La máquina debe
permanecer encendida; después de reiniciarla hay que recrear ambas sesiones
`screen` con los comandos anteriores.
