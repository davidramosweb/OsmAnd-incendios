# RELEASE-001 — Desplegar y aceptar el MVP

**Estado:** en aceptación  
**Dependencias:** [OSMAND-003](./OSMAND-003-paquete-osf.md)  
**Siguiente:** ninguno; cierre del MVP

## Objetivo

Desplegar el Worker, Static Assets, KV, cron y paquete OsmAnd validados, y ejecutar una aceptación completa sin añadir funcionalidades nuevas.

## Alcance

- Crear namespace KV de producción y aplicar bindings.
- Desplegar mediante Wrangler y registrar versión/configuración.
- Activar el Cron horario.
- Esperar o provocar de forma controlada una primera captura válida.
- Comprobar web, estado, salud, teselas y `.osf` desde la URL pública.
- Ejecutar la matriz final en Android e iOS.
- Verificar comportamiento ante fallo de fuente y cambio de día.
- Documentar rollback al despliegue anterior y desactivación del cron.
- Revisar que el consumo previsto cabe en límites gratuitos.

## Fuera de alcance

- Dominio propio obligatorio.
- CI/CD completo.
- Alertas externas, historial, previsión o mapa web.
- Cambios de geometría o formato de plantilla.

## Entregables

- URL pública del MVP.
- Versión desplegada y configuración reproducible.
- Matriz de aceptación firmada/fechada.
- Runbook mínimo de fallo y rollback.
- Lista priorizada de mejoras posteriores, sin implementarlas.

## Criterios de aceptación

- [ ] El cron obtiene y publica siete niveles válidos cada hora.
- [ ] Un fallo de fuente no publica datos parciales.
- [ ] A medianoche, datos anteriores se muestran grises.
- [ ] Las teselas coloreadas son correctas y transparentes en Android e iOS.
- [ ] Nivel 3 aparece rojo y la documentación explica el cierre preventivo propio.
- [ ] Niveles 1/2 no se presentan como confirmación de apertura.
- [x] La web muestra fecha, leyenda, atribución y aviso no oficial.
- [ ] El `.osf` se instala desde la URL pública.
- [x] `/health` diferencia actual, obsoleto y no disponible.
- [ ] El rollback se prueba sin perder el último estado válido.
- [x] Assets y peticiones permanecen dentro de los límites asumidos para el MVP.

## Cierre del MVP

Registrar fecha, versiones de OsmAnd, `geometry_version`, hash de plantillas, versión del Worker y hash del `.osf`. Cualquier mejora posterior debe abrir un ticket nuevo y no reabrir el alcance de este release.

## Avance de despliegue para OSMAND-003 — 2026-07-18

Con autorización explícita del usuario se autenticó Wrangler, se comprobó que
no existían Worker o namespaces previos y se crearon:

- KV producción `PREVIFOC_STATE`: `855480b5380e47b1881e1f178c6a92e7`;
- KV preview: `3584deea553c46d29ddcde14661506d6`.

`wrangler.jsonc` fija ambos IDs, el custom domain
`previfoc.davidramosweb.com`, Static Assets y el cron horario `7 * * * *`. La
versión activa es `578e178b-7544-41a9-9475-cd063929f08c`; la versión anterior
recuperable es `c9ff2a89-6e1d-4d7e-b91f-520e95496e2c`. El informe operativo y
runbook están en `data/release-001/REPORT.md`.

La primera captura actual se generó mediante las mismas funciones de ingesta,
normalización, hash y validación que usa el Worker y se escribió una sola vez
en producción. No se creó una ruta administrativa ni se aumentó la frecuencia
del cron. El KV contiene únicamente la clave `current`.

La matriz pública pasa raíz, salud, estado, `.osf` y tesela cubierta con HTTP
200; el instalador conserva su hash y la tesela dinámica informa estado actual.
El antiguo scaffold `index 2.html` fue excluido del manifiesto y devuelve 404,
sin borrar el archivo local. El staging final contiene 9.512 assets.

Verificación local final: typecheck correcto, 50 pruebas Vitest/workerd, 6
pruebas Python, dry run de 35,46 KiB (8,95 KiB gzip) y bundle de 36.309 bytes.

Este avance no cierra RELEASE-001: faltan observar una ejecución cron real,
las pruebas Android/iOS, fallo de fuente, medianoche, rollback efectivo y la
aceptación completa.
