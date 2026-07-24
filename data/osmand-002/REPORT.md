# OSMAND-002 — Evidencia de validación en dispositivos

## iPhone — captura general de overlay

- Fecha de entrega: 2026-07-18.
- Plataforma: iPhone físico, confirmada explícitamente por el usuario.
- Resultado comunicado: «parece que funciona bien».
- Aplicación: OsmAnd iOS 5.3.3, inferida del `User-Agent`
  `OsmAndIOS_5.3.3` observado en el origen; falta confirmarla en la pantalla de
  información de la app.
- Modelo de iPhone y versión de iOS: no comunicados.
- Método de alta: no comunicado.
- Archivo: [ios-overview-2026-07-18.jpg](./evidence/ios-overview-2026-07-18.jpg).
- Formato y dimensiones: JPEG RGB sRGB, 588 × 1280 px.
- SHA-256:
  `267cc2b3b49ea6bf003cab1c6b767272825794895fb32e362bd53563c200bef8`.
- Integridad: el archivo guardado es idéntico byte a byte al adjunto recibido;
  no se recortó, redimensionó, recomprimió ni anotó.

### Observación visual acreditada

La captura muestra la fuente activa como superposición sobre el mapa vectorial
de OsmAnd. La geometría sigue la Comunitat Valenciana desde Castellón hasta
Alicante y encaja con la costa. Los límites exteriores e internos son visibles;
la secuencia norte-sur y la costa descartan una inversión Y aparente. El relleno
es semitransparente: carreteras, nombres, costa y otros símbolos del mapa base
siguen visibles. No se aprecia fondo blanco, opacidad completa, halo ni seam en
esta vista general.

La captura contiene otros POI, avisos y trazados que no pertenecen a PREVIFOC;
su solapamiento con algunos rótulos no se atribuye a esta fuente.

### Límites de la evidencia

La escala visible es de 50 km, pero la captura no registra el número de zoom de
OsmAnd. Por sí sola no prueba z6, detalle z14, sobrezoom posterior, continuidad
a máxima ampliación, borrado de caché ni recarga causal tras cinco minutos. No
hay una captura equivalente de Android.

