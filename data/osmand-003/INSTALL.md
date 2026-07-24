# Instalar PREVIFOC en OsmAnd

Artefacto: `previfoc.osf` 2.0.0. Instala dos fuentes XYZ remotas,
**PREVIFOC — Hoy (no oficial)** y **PREVIFOC — Mañana (previsión)**,
pensadas para usarse alternativamente como superposición sobre el mapa vectorial de OsmAnd. El
paquete no contiene teselas ni el estado diario.

La URL `https://previfoc.davidramosweb.com` está operativa desde el despliegue
del 2026-07-18. La página, el instalador, el estado y las teselas usan el mismo
origen definitivo.

## Android

1. En OsmAnd, active `Menú → Complementos → Mapas en línea` si aún no lo está.
2. Descargue `previfoc.osf` desde la página pública y ábralo con OsmAnd.
3. Revise que la importación enumera el complemento y una fuente de mapas;
   pulse **Importar**.
4. Abra `Configurar mapa → Superposición` y seleccione
   **PREVIFOC — Hoy (no oficial)** o **PREVIFOC — Mañana (previsión)**.
   Mantenga el mapa vectorial como mapa principal.
5. En la ficha de la fuente, compruebe zoom 6–14, Pseudo-Mercator/XYZ y
   caducidad de 60 minutos. No active Y invertida.
6. Para forzar una comprobación limpia, use la acción **Borrar todas las
   teselas** de la fuente y vuelva a mostrar la Comunitat Valenciana.

Los nombres pueden variar ligeramente según la versión y el idioma. Android
requiere el complemento Mapas en línea; esa activación previa no es necesaria
en iOS.

## iOS

1. Descargue `previfoc.osf` en Safari o Archivos y elija
   `Compartir → Abrir con OsmAnd`.
2. Importe el complemento y su fuente cuando OsmAnd muestre el contenido.
3. Abra `Configurar mapa → Overlay/Underlay → Overlay` y seleccione
   **PREVIFOC — Hoy (no oficial)** o **PREVIFOC — Mañana (previsión)**.
4. Mantenga el mapa vectorial como principal y active **Mostrar símbolos del
   mapa** si desea que sus rótulos queden por encima de la capa.
5. Compruebe zoom 6–14 y caducidad de 60 minutos en la edición de la fuente.
6. Para una descarga limpia, use **Clear cache / Borrar caché** y vuelva a
   mostrar la zona.

## Reinstalación

El paquete conserva el identificador `com.davidramosweb.previfoc` y usa versión
de plugin `2`. Como la versión 1 registraba una fuente con otro nombre, elimine
primero `PREVIFOC (no oficial)` en `Mapas y recursos → Local → Fuentes de mapas`
y después importe la versión 2. En reinstalaciones posteriores seleccione
**Reemplazar** y no **Conservar ambos**.

## Comprobación en ambos sistemas

Después de instalar desde cero:

- verifique que el mapa base, caminos y nombres siguen visibles;
- recorra z6, z10 y z14 y confirme que no hay eje Y invertido ni fondo opaco;
- abra los enlaces de instalación, atribución y limitaciones de la descripción;
- espere más de 60 minutos, vuelva a la misma tesela y compruebe una petición
  nueva en el Worker;
- repita la importación y confirme que solo queda una fuente con el nombre
  estable.

Registre versión de OsmAnd, sistema operativo, modelo, resultado y hora. Las
capturas mínimas son: pantalla de importación, fuente seleccionada como overlay
y ficha con la caducidad. No reutilice la captura de OSMAND-002 como prueba de
este paquete: acredita la fuente temporal, no la importación del `.osf` final.

## Limitaciones

Las fuentes ráster no ofrecen objetos pulsables, leyenda fija ni actualización en
segundo plano. OsmAnd vuelve a solicitar una tesela caducada cuando se necesita
y puede mostrar una copia ya almacenada durante una caída. El nivel 3 se trata
como cierre preventivo propio solo en la capa de hoy; en la capa de mañana es
únicamente una previsión de riesgo. Los niveles 1 y 2 no confirman apertura. Este es
un servicio independiente y no oficial: prevalecen autoridades, resoluciones,
señalización y la fuente oficial 112CV.
