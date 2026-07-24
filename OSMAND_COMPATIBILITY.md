# Compatibilidad con OsmAnd

Verificación documental realizada el **2026-07-17** contra la documentación oficial vigente de OsmAnd. Queda pendiente una prueba física con las versiones de tienda de Android e iOS; se incluye como criterio de aceptación de la Fase 0.

Fuentes principales:

- [Raster Maps (Online / Offline)](https://osmand.net/docs/user/map/raster-maps)
- [Import / Export](https://osmand.net/docs/user/personal/import-export)
- [Custom Package](https://osmand.net/docs/user/plugins/custom)
- [Tiles SQLite Format](https://osmand.net/docs/technical/osmand-file-formats/osmand-sqlite)
- [Maps & Resources](https://docs.osmand.net/es/docs/user/personal/maps-resources/)

## Conclusión

El denominador común real entre Android e iOS es una fuente de **teselas ráster XYZ en Web Mercator**, instalada una vez de forma manual —preferentemente mediante `.osf`— y configurada como superposición. OsmAnd refresca las teselas visibles después del tiempo de caducidad configurado, de modo que los datos pueden actualizarse sin reinstalar el paquete.

No hay soporte documentado equivalente para consumir directamente un `FeatureCollection` GeoJSON dinámico, descubrir un WMS/WMTS ni consultar atributos al pulsar un polígono. La documentación advierte expresamente que los objetos de una capa ráster no son pulsables.

Por tanto:

- **visualización en OsmAnd**: XYZ PNG transparente;
- **distribución de la configuración**: `.osf` con `MAP_SOURCES`;
- **datos interoperables e interacción fuera de OsmAnd**: GeoJSON y `/status`;
- **offline opcional**: descarga de teselas o `.sqlitedb` compatible con OsmAnd, no MBTiles sin conversión.

## Matriz de formatos

| Formato/protocolo | Android | iOS | Actualización directa | Instalación | Pulsar zona | Dictamen |
|---|---|---|---|---|---|---|
| XYZ ráster `{z}/{x}/{y}.png` | Sí; requiere habilitar el complemento Mapas en línea | Sí; disponible por defecto según la documentación | Sí, al volver a mostrar teselas caducadas | Manual una vez; fuente o `.osf` | No | **Formato MVP** |
| TMS con Y invertida | Posible mediante `inverted_y` en configuración/SQLite; no es un descubridor TMS | Debe verificarse con `.osf`; el formulario común no documenta el selector | Sí si queda configurado como fuente remota | Manual | No | Compatible de forma condicionada; no aporta ventaja |
| WMTS | Sin cliente de capacidades documentado; un template REST Web Mercator puede tratarse como XYZ | Igual | Solo si se reduce a URL de tesela | Manual | No | No publicar solo WMTS |
| WMS | No hay alta genérica nativa documentada; el formato SQLite menciona una regla `wms_tile` con proxy | No hay soporte directo documentado | Condicionada a proxy/conversión | Compleja | No en OsmAnd | No recomendado para el cliente |
| OsmAnd SQLite `.sqlitedb` | Sí | Sí | Una fuente SQLite puede conservar URL y caducidad; un archivo puramente offline requiere actualización manual | Importación de archivo/OSF | No | Opción offline secundaria |
| MBTiles `.mbtiles` | No aparece en formatos importables oficiales; esquema distinto | Igual | No | Requiere convertir a SQLite de OsmAnd | No | No distribuir directamente |
| GeoJSON | No figura como formato de importación de capa en la documentación actual | Igual | No | No documentada | No aplicable | API complementaria, no capa OsmAnd |
| KML/KMZ/GPX | Sí, KML/KMZ se convierten a GPX | Sí | No para un feed remoto | Manual | Elementos de track/waypoints, no polígonos temáticos dinámicos equivalentes | No sirve como capa de riesgo rellena |
| Mapa vectorial `.obf` | Sí | Sí | Archivo descargable; no feed diario transparente | Manual/OSF/descarga sugerida | Puede aportar contexto vectorial según codificación | Futuro, no MVP |
| `.osf` | Sí | Sí | El paquete no se actualiza solo, pero la fuente XYZ incluida sí | Manual una vez | Depende del recurso; el XYZ no | **Distribución recomendada** |

## Hechos verificados por la documentación oficial

### Capas ráster en ambas plataformas

- En Android hay que habilitar el complemento **Online maps / Mapas en línea**.
- En iOS la función de mapas ráster funciona por defecto.
- Ambas plataformas admiten una fuente ráster como mapa principal, overlay y underlay, con control de transparencia.
- La URL admite `{z}/{x}/{y}` o los equivalentes `{0}/{1}/{2}`.
- La fuente debe entregar teselas en proyección Mercator; para el MVP se usará EPSG:3857, XYZ estándar, Y no invertida.
- El formulario permite definir el tiempo de expiración en minutos. Tras expirar, una tesela almacenada todavía puede mostrarse, pero se vuelve a descargar cuando se necesita.
- Las teselas pueden guardarse como imágenes individuales o en SQLiteDB.

### Descarga y actualización offline

Ambas plataformas permiten descargar o actualizar un área cuando la fuente en línea está seleccionada como mapa principal. La documentación indica una diferencia: seleccionar separadamente overlay o underlay para la operación de descarga está disponible solo en Android. La prueba en iOS debe confirmar el flujo exacto y si la capa vuelve a quedar como overlay después de descargarla.

Esto no equivale a una sincronización en segundo plano. El refresco por caducidad ocurre cuando las teselas se visualizan; OsmAnd puede seguir mostrando una copia de caché hasta entonces.

### Limitación de interacción

La documentación de Raster Maps señala que no se puede pulsar un objeto concreto del ráster para obtener información. Aunque un WMS externo soporte `GetFeatureInfo`, OsmAnd no documenta que ejecute esa operación para una capa personalizada.

Consecuencias:

- no habrá ficha de polígono al tocar la zona en el MVP;
- el nivel, código de zona y señales de obsolescencia deben estar en el propio dibujo;
- el detalle se ofrecerá en una página/API enlazada desde la descripción del complemento, usando `/status?lat=…&lon=…`;
- una futura advertencia de ruta debe calcularse en el backend, no depender del motor de capas ráster de OsmAnd.

## Evaluación específica

### XYZ ráster

Es la única alternativa que satisface simultáneamente Android, iOS y actualización remota sin fork. Usar:

```text
https://mapa.example/tiles/{z}/{x}/{y}.png
```

Parámetros previstos:

- Web Mercator esférico;
- XYZ, Y no invertida;
- PNG32 transparente, 256×256 px;
- zoom mínimo 6, máximo 14;
- caducidad en el cliente: objetivo 15 minutos, a confirmar exportando la fuente desde ambas apps;
- overlay, no mapa principal.

La configuración debe generarse primero en una app y exportarse para estudiar el `.osf` real, en vez de asumir que todos los campos internos conservan las mismas unidades en Android e iOS.

### TMS

TMS invierte el eje Y respecto de XYZ. Los formatos de configuración de OsmAnd incluyen `inverted_y`, por lo que técnicamente puede representarse. Sin embargo, no existe ventaja para este proyecto: el backend controla la salida y puede publicar XYZ estándar. TMS añade una posibilidad de configuración errónea y debe quedar como endpoint opcional de compatibilidad, no como fuente del `.osf`.

### WMTS

OsmAnd no documenta un diálogo que lea `GetCapabilities`. Si un WMTS ofrece un template REST exactamente equivalente a teselas Web Mercator, la URL resultante puede introducirse como si fuera XYZ. Matrices, identificadores, escalas o ejes diferentes requieren un adaptador del servidor. Publicar WMTS puede ser útil para clientes GIS, pero no debe ser la única interfaz para OsmAnd.

### WMS

El formato SQLite técnico menciona `rule = wms_tile`, que utiliza un proxy para convertir una solicitud de tesela en una petición WMS. Eso no constituye soporte WMS directo y portable. Implica un servicio intermediario, complica caché y añade puntos de fallo. Si se ofrece WMS por interoperabilidad, el mismo backend debe publicar además XYZ.

### MBTiles y SQLite de OsmAnd

La importación oficial enumera `.sqlitedb`. El esquema de OsmAnd deriva de BigPlanet y añade una tabla `info`, URL, expiración, numeración, Y invertida y tiempo de descarga. Un MBTiles estándar usa otro esquema y convenciones; cambiar la extensión no es una conversión válida.

Uso previsto:

- para conexión normal, dejar que OsmAnd gestione su caché SQLite a partir de XYZ;
- para un paquete de emergencia offline, convertir y validar a `.sqlitedb` OsmAnd;
- publicar fecha y validez dentro de ese paquete, porque no se actualizará mágicamente si no conserva una URL remota y expiración compatibles.

### GeoJSON

La lista oficial actual de importación incluye GPX, KML/KMZ, OBF, SQLitedb y OSF, no GeoJSON. Incluso si una versión concreta aceptara un GeoJSON por una vía no documentada, no sería una base mantenible para ambos sistemas.

El GeoJSON se mantiene porque es el mejor contrato para:

- inspección y control de calidad;
- web y otros clientes GIS;
- consulta puntual;
- intersección futura con rutas;
- creación de teselas y mapas descargables.

### Mapas vectoriales `.obf`

OsmAnd importa mapas vectoriales OBF en ambas plataformas. Podrían ofrecer estilos y objetos consultables, pero el pipeline de compilación y la actualización diaria serían más complejos y la distribución seguiría siendo por archivos. Se reserva para una fase posterior, especialmente si se necesita funcionamiento completamente offline o integración con el enrutamiento.

### Paquete `.osf`

Un `.osf` es un ZIP con `items.json` y recursos. Puede incluir una entrada `MAP_SOURCES` para registrar la fuente XYZ y enlaces descriptivos. Es el mecanismo recomendado porque reduce errores de escritura y funciona como paquete compartible en ambas plataformas.

El `.osf` debe contener solo configuración estable y registra dos fuentes seleccionables:

- `PREVIFOC — Hoy`, con relleno sólido;
- `PREVIFOC — Mañana`, con trama diagonal y semántica de previsión de riesgo.

Además incluye:

- nombre no oficial de la capa;
- URL XYZ estable;
- zoom y proyección;
- política de caducidad;
- icono y atribución;
- enlace a leyenda, metadatos, privacidad y aviso de responsabilidad.

No debe incluir el estado diario como dato fijo. La actualización diaria llega por las teselas remotas.

## Procedimiento previsto de instalación

### Android

1. Instalar OsmAnd y habilitar `Menú → Complementos → Mapas en línea`.
2. Abrir `previfoc.osf` con OsmAnd e importar el complemento/fuente.
3. Activar la fuente en `Configurar mapa → Superposición`.
4. Mantener el mapa vectorial de OsmAnd como mapa principal.
5. Ajustar la transparencia solo si se desea; el PNG ya lleva alpha.
6. Abrir el enlace de metadatos/leyenda desde la descripción y comprobar fecha.
7. Tras un cambio oficial, esperar más que el tiempo de expiración, volver a visualizar el área y confirmar que cambia una tesela.

Alternativa de POC: usar la [URL mágica de OsmAnd](https://osmand.net/docs/user/map/raster-maps#magic-url-to-install-map-source), que registra nombre, URL y zoom, pero ofrece menos control y una experiencia de atribución peor.

### iOS

1. Abrir `previfoc.osf` desde Archivos, Safari, correo o mensajería y elegir OsmAnd.
2. Restaurar/importar el complemento o la fuente.
3. Seleccionarla en `Configurar mapa → Overlay/Underlay → Overlay`.
4. Mantener el mapa vectorial como principal y activar “Mostrar símbolos del mapa” para que nombres y caminos sigan visibles.
5. Confirmar el refresco tras la caducidad y el comportamiento sin conexión.

El procedimiento exacto debe documentarse con capturas obtenidas en la versión de App Store usada en Fase 0. La interfaz puede variar respecto de la documentación.

## Leyenda y fecha de actualización dentro de OsmAnd

Una fuente de teselas no dispone de un panel dinámico fijo. `legend.png` y `metadata.json` no aparecerán automáticamente en la pantalla de mapa. Para aproximar el requisito sin fork:

- incluir código de zona, nivel numérico y símbolo de tormenta en el propio mapa a zoom 6–9;
- añadir una marca corta `Actualizado: DD/MM HH:mm` junto a las etiquetas generales a zoom 6–8;
- hacer visible `DATOS OBSOLETOS` como trama/marca repetida si el snapshot caduca;
- enlazar `legend.png` y una página accesible desde la descripción del `.osf`;
- no repetir texto en cada tesela a zoom alto, porque ocultaría caminos.

**Limitación no resoluble con una fuente XYZ simple:** no se puede garantizar que una leyenda y un reloj estén siempre fijos en pantalla. Este punto debe aceptarse como limitación de OsmAnd o requeriría un cambio/fork, expresamente fuera de alcance.

## Plan de pruebas cruzadas

Matriz mínima en un Android y un iPhone físicos:

| Prueba | Android | iOS | Criterio |
|---|---|---|---|
| Importar `.osf` | Pendiente | Pendiente | Fuente visible sin editar JSON |
| Seleccionar como overlay | Pendiente | Pendiente | Mapa vectorial y caminos permanecen visibles |
| URL XYZ con PNG transparente | Pendiente | Pendiente | Sin fondo blanco/negro |
| Zoom 6–14 y sobrezoom | Pendiente | Pendiente | Sin desaparición inesperada ni pixelado inaceptable |
| Expiración 15 min | Pendiente | Pendiente | Una tesela modificada se vuelve a pedir al visualizarla |
| Caché sin conexión | Pendiente | Pendiente | Se muestra lo ya visitado con señal de posible obsolescencia |
| Borrar caché | Pendiente | Pendiente | La capa vuelve a descargarse correctamente |
| Descarga de un área | Pendiente | Pendiente | Procedimiento y límites documentados |
| Leyenda y enlace | Pendiente | Pendiente | Accesibles desde el complemento |
| Toque sobre zona | No esperado | No esperado | Se documenta que no hay ficha de objeto |

Capturar durante la prueba:

- versión exacta de OsmAnd y sistema operativo;
- `.osf` exportado por cada plataforma;
- peticiones observadas en el servidor, incluyendo `User-Agent`, caché y revalidación;
- comportamiento con HTTP `404`, `429`, `500`, timeout y tesela transparente;
- tiempo real hasta que aparece una actualización.

## Limitaciones conocidas

1. Los polígonos ráster no son interactivos.
2. No hay leyenda dinámica fija ni reloj fijo en la UI de OsmAnd.
3. La actualización por caducidad ocurre al visualizar; no es una garantía de sincronización en segundo plano.
4. Una tesela cacheada puede seguir viéndose durante una caída. Por eso debe llevar señales de obsolescencia cuando el servidor ya conoce el estado stale.
5. Un `.osf` se instala manualmente; después, la fuente remota sí se actualiza.
6. La descarga de overlay/underlay difiere entre Android e iOS según la documentación.
7. Ninguna de estas capacidades convierte el servicio en fuente oficial ni en autoridad sobre la circulación.
