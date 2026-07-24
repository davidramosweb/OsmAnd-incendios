# WEB-001 — Crear la página informativa y la leyenda

**Estado:** completado  
**Dependencias:** [WORKER-004](./WORKER-004-recoloreado-cache.md)  
**Siguiente:** [OSMAND-003](./OSMAND-003-paquete-osf.md)

## Objetivo

Publicar una página estática sencilla que explique la capa, muestre el estado actual y permita instalarla sin convertir la web en otra aplicación cartográfica.

## Alcance

- HTML, CSS y JavaScript sin framework ni proceso SSR.
- Consultar `/status.json` y mostrar hora, actualidad y siete niveles.
- Incluir una leyenda con los tres colores y el estado gris.
- Incluir atribución 112CV/Generalitat e ICV según las condiciones documentadas.
- Mostrar el aviso de servicio independiente y no oficial.
- Explicar exactamente la regla conservadora de cierre y que nivel 1/2 no confirma apertura.
- Enlazar fuente oficial, descarga `.osf` y guía de instalación.
- Diseñar para móvil, teclado y lectores de pantalla.

## Texto obligatorio

> Servicio no oficial. Criterio preventivo propio: cuando PREVIFOC publica nivel 3, esta capa trata las pistas y sendas forestales de la zona como cerradas al público. Los niveles 1 y 2 no confirman que una vía esté abierta. Consulte las autoridades y resoluciones aplicables.

## Fuera de alcance

- Mapa web interactivo.
- Geolocalización.
- Historial, previsión o notificaciones.
- Analítica de terceros.

## Entregables

- Página principal estática.
- Leyenda accesible.
- Página/fragmento de instalación y limitaciones.
- Estados visuales para actual, obsoleto y no disponible.

## Criterios de aceptación

- [x] La página funciona sin JavaScript para contenido legal y de instalación esencial.
- [x] Con JavaScript muestra las siete zonas y fecha de `/status.json`.
- [x] Dato obsoleto queda claramente diferenciado y no conserva apariencia de actualidad.
- [x] No se usa solo color para comunicar cierre.
- [x] El aviso obligatorio aparece cerca de la leyenda.
- [x] No se denomina oficial al servicio ni a la geometría derivada.
- [x] Pasa una revisión básica de teclado, contraste y tamaño móvil.

## Cierre de sesión

OSMAND-003 utilizará las URLs definitivas de esta página para atribución, ayuda y avisos dentro del paquete.

## Cierre de WEB-001 — 2026-07-18

Se sustituyó el marcador técnico por una página estática responsive en
`static/index.html`, `static/styles.css` y `static/app.js`, sin framework,
dependencias de producción, mapa interactivo ni analítica. La raíz `/` sirve
el mismo documento que `/index.html`; el proceso de staging copia y verifica
por hash todos los assets estáticos, además de las teselas congeladas.

El HTML sin JavaScript contiene el aviso obligatorio, leyenda textual, regla
preventiva, limitaciones, atribución 112CV/Generalitat e ICV/Generalitat con
CC BY 4.0, enlaces a las fuentes y guía de instalación Android/iOS. Se reserva
`/previfoc.osf` como URL estable del instalador que generará OSMAND-003; la
página indica expresamente que el artefacto aparecerá ahí después de su
validación en ambos sistemas.

La mejora progresiva consulta `/status.json`, exige exactamente las zonas
53–59 y niveles 1–3, muestra la hora fuente en `Europe/Madrid` y distingue:

- actual: colores y texto de nivel, con “cierre preventivo” para nivel 3 y
  “no confirma apertura” para niveles 1/2;
- obsoleto: cabecera de advertencia, siete niveles publicados rotulados como
  obsoletos y todas las marcas visuales en gris;
- no disponible o inválido: estado y siete zonas en gris, con indicación de
  consultar 112CV.

La revisión básica incluye enlace de salto, navegación semántica, foco visible,
región viva, significado textual además del color, controles de al menos 48 px,
breakpoints a 900/680/380 px, `prefers-reduced-motion` y modo de colores
forzados. Los contrastes principales medidos son 13,08:1 (texto), 5,94:1
(texto secundario), 6,03:1 (rótulos), 12,26:1 (botones), 6,22:1 (estado gris)
y 4,78:1 (símbolo sobre rojo). Los navegadores conectados bloquearon por
política la apertura de `localhost`, así que la revisión visual automática no
produjo captura; el DOM, los estados y los breakpoints se revisaron mediante
fuente y pruebas del Worker.

Verificación final:

```sh
pnpm typecheck
WRANGLER_LOG_PATH=/tmp/web001-vitest-final.log pnpm test
pnpm check:assets
WRANGLER_LOG_PATH=/tmp/web001-dry-run.log pnpm deploy:dry-run
```

Resultados: typecheck correcto; 5 ficheros y 49 pruebas Vitest/workerd
correctas; staging de 9.511 assets (9.507 teselas más transparente, HTML, CSS
y JavaScript) correcto; dry run con `Total Upload: 34.58 KiB / gzip: 8.78
KiB` y bundle de 35.413 bytes frente a la guarda de 1 MiB. No se desplegó ni
se generó anticipadamente el `.osf` de OSMAND-003.
