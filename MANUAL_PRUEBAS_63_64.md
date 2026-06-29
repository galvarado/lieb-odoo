# Manual de Pruebas — Spec 6.3 Surtido a Tienda / Spec 6.4 Recepción y Rechazo

**Prerequisitos antes de empezar**

- Módulo `lieb_puros_heridos` instalado/actualizado.
- Almacén central creado (ej. código `TSF`).
- Al menos una tienda creada como almacén independiente (ej. `TIENDA1`).
- Stock disponible de al menos un puro variante Línea en `TSF/Existencias`.
- Stock disponible de al menos un puro variante Herido 20% o Herido 40% en `TSF/Heridos`.
- Usuario con grupo **Stock / Usuario** para operaciones básicas.
- Usuario con grupo **Aprobador de Actas de Tienda** para el escenario 6.4-D.

---

## 6.3.A — Surtido sin requisición (flujo directo)

### Crear y enviar el surtido

Inventario → Surtidos a Tienda → Nuevo

- **Fecha:** hoy
- **Almacén Origen:** TSF
- **Tienda Destino:** TIENDA1
- **Chofer:** Juan Pérez
- **Firma Chofer:** *(opcional, subir imagen)*
- Agregar línea:
  - Producto: `PURO MONTECRISTO 2 14.26 GRAMOS [Línea]`
  - Cantidad: 20
- Agregar línea:
  - Producto: `PURO MONTECRISTO 2 14.26 GRAMOS [Herido 20%]`
  - Cantidad: 5
- Agregar línea:
  - Producto: `PURO MONTECRISTO 2 14.26 GRAMOS [Tolerable]`
  - Cantidad: 3
- Verificar que la columna **Condición** muestra el valor correcto por línea.
- Verificar que **Ubicación Origen** y **Ubicación Destino** se calculan automáticamente:
  - Línea → `TSF/Existencias` → `TIENDA1/Existencias`
  - Herido 20% → `TSF/Heridos` → `TIENDA1/Heridos`
  - Tolerable → `TSF/Heridos` → `TIENDA1/Existencias`
- Clic **Enviar a Tienda** → confirmar diálogo.

### Verificar stock en tránsito

Inventario → En Tránsito

- Debe aparecer el surtido `SURT/XXXX/0001` con estado **En Tránsito** y badge naranja.

Inventario → Configuración → Ubicaciones → buscar `Tránsito Surtido` → Existencias actuales

- Debe mostrar las 3 líneas con sus cantidades sumadas.

### Verificar pickings generados

Desde el form del surtido → botón **Salidas**

- Deben existir pickings `ALM→Tránsito` en estado **Hecho**.
- Los pickings de salida están agrupados por par (src, dest): hasta 3 pickings según combinaciones de líneas.

Desde el form del surtido → botón **Entradas (X pendientes)**

- Deben existir pickings `Tránsito→TIENDA1` en estado **Listo**.

---

## 6.3.B — Surtido con requisición previa

### Crear la requisición en tienda

Inventario → Requisiciones de Surtido → Nueva

- **Tienda Solicitante:** TIENDA1
- **Responsable:** usuario actual
- Agregar línea:
  - Producto: `PURO MONTECRISTO 2 14.26 GRAMOS [Línea]`
  - Cantidad Solicitada: 10
- Clic **Enviar Solicitud** → estado cambia a **Enviada** y se asigna referencia `REQSURT/XXXX/0001`.

### Crear surtido desde la requisición

Desde el form de la requisición → clic **Crear Surtido**

- Se abre form de `surtido.tienda` pre-llenado con las líneas.
- El campo **Requisición** muestra `REQSURT/XXXX/0001`.
- Completar **Almacén Origen** (TSF) y **Chofer**.
- Clic **Enviar a Tienda**.

### Verificar vínculo

Volver a la requisición → botón **Surtidos (1)** → navega al surtido generado.

Verificar que estado de requisición cambió a **Surtida**.

---

## 6.4.A — Recepción completa en tienda

### Validar picking entrante

Inventario → Operaciones → Transferencias (desde TIENDA1 o buscar por origen `SURT/XXXX/0001`)

- Abrir el picking `Tránsito Surtido → TIENDA1/Existencias`.
- Verificar que las cantidades están asignadas.
- Clic **Validar** → confirmar.

### Verificar stock en tienda

Inventario → Reportes → Existencias → filtrar por `TIENDA1`

- `TIENDA1/Existencias`: 20 unidades `[Línea]` + 3 unidades `[Tolerable]`
- `TIENDA1/Heridos`: 5 unidades `[Herido 20%]`

### Verificar estado del surtido

Inventario → Surtidos a Tienda → abrir `SURT/XXXX/0001`

- Estado debe ser **Recibido** (cambia automáticamente cuando todos los pickings IN están hechos).

---

## 6.4.B — Recepción parcial con backorder

Abrir el picking entrante `Tránsito→TIENDA1/Existencias` (si hay uno de 20 piezas Línea):

- Editar la columna **Cantidad Hecha** y poner 15 (en lugar de 20).
- Clic **Validar** → Odoo pregunta si crear backorder → confirmar **Crear backorder**.

Resultado esperado:
- Picking original: estado **Hecho** con 15 unidades.
- Nuevo picking backorder: 5 unidades restantes en estado **Listo**.
- `Tránsito Surtido` aún muestra 5 unidades de esa variante.

---

## 6.4.C — Rechazo por daño en tránsito

### Registrar rechazo

Abrir el picking entrante en estado **Listo** (antes de validar):

- Clic en botón **Rechazar Piezas** (botón stat box en la parte superior).
- Se abre el wizard **Rechazar Piezas**.
  - **Tipo de Rechazo:** Daño en tránsito
  - En la línea del producto afectado:
    - **Cantidad a Rechazar:** 2
    - **Motivo:** Daño en capa
    - **Nota:** "Llegó aplastado en caja inferior"
- Clic **Confirmar Rechazo**.

### Verificar resultado

Inventario → Reportes → Existencias → filtrar por `TSF/Revisión-Dañados`

- Debe aparecer `PURO MONTECRISTO 2 14.26 GRAMOS [Línea]` con 2 unidades.
- **Importante:** el producto regresa como variante **Línea** (la tienda no clasifica).

Inventario → Configuración → Ubicaciones → `Tránsito Surtido` → Existencias actuales

- La cantidad de esa variante se redujo en 2.

### Verificar motivo en el picking de retorno

Inventario → Operaciones → Transferencias → buscar picking con origen `SURT/XXXX/0001` hacia `Revisión-Dañados`

- Abrir el picking → ver movimiento → campo **Motivo de Rechazo**: "Daño en capa"
- Campo **Nota de Rechazo**: el texto ingresado.

### Continuar el flujo (para el almacén)

El clasificador en almacén ve las piezas en `TSF/Revisión-Dañados`.

Inventario → Actas de Clasificación → Nueva

- **Momento:** 2 – Recepción en Tienda
- **Ubicación Origen:** TSF/Revisión-Dañados
- Agregar líneas con cantidades por condición → validar (flujo normal de acta).

---

## 6.4.D — Rechazo por discrepancia (error de surtido)

Abrir picking entrante antes de validar → **Rechazar Piezas**

- **Tipo de Rechazo:** Discrepancia de surtido
- Línea afectada:
  - **Cantidad a Rechazar:** 3
  - **Motivo:** Error de surtido
  - **Nota:** "Llegaron puros de formato diferente al solicitado"
- **Confirmar Rechazo**.

### Verificar destino de retorno

Para variante Línea: las 3 piezas regresan a `TSF/Existencias` (no a Revisión-Dañados).

Para variante Herido 20%: las piezas regresan a `TSF/Heridos`.

*La discrepancia no pasa por clasificación — el almacén recibe sus piezas de vuelta directamente.*

---

## 6.4.E — Tolerable detectado en tienda (acta simplificada)

**Escenario:** la encargada detecta que 2 puros de la entrega tienen daño menor tolerable y decide conservarlos sin devolver al almacén.

### Registrar tolerable

Abrir el picking entrante (puede estar en estado **Hecho** también) → botón **Registrar Tolerable**

- Se abre un **Acta de Clasificación** con:
  - **Momento:** 2 – Recepción en Tienda
  - **Ubicación Origen:** TIENDA1/Existencias (precargada del picking)
  - Solo visible la columna **Tolerable** (Herido 20%, Herido 40% y Picado están ocultos).

- Agregar línea:
  - Producto: `PURO MONTECRISTO 2 14.26 GRAMOS`
  - Tolerable: 2
- Clic **Enviar a Aprobación**.

### Aprobar (requiere grupo Aprobador de Actas de Tienda)

- Clic **Aprobar** → el sistema valida que el usuario pertenece a `group_acta_approver_tienda`.
- Una sola aprobación es suficiente → estado pasa a **Aprobada**.

> **Nota:** Un usuario con ambos grupos (Almacén y Tienda) puede aprobar en cualquiera de los dos flujos.

- Clic **Validar**.

### Verificar resultado

Inventario → Reportes → Existencias → filtrar por `TIENDA1`

- `TIENDA1/Existencias`: se reducen 2 unidades `[Línea]` y aparecen 2 unidades `[Tolerable]`.
- No hay movimiento hacia el almacén — el stock permaneció en tienda.

---

## 6.3.C — Cancelar un surtido en tránsito

Inventario → Surtidos a Tienda → abrir surtido en estado **En Tránsito**

- Clic **Cancelar** → confirmar diálogo.

Verificar:
- Los pickings IN pendientes se cancelan.
- Se genera un picking de reversa para los pickings OUT ya validados (stock regresa de `Tránsito Surtido` a los orígenes).
- `Tránsito Surtido` queda en cero para este surtido.
- Estado del surtido: **Cancelado**.

---

## Resumen de ubicaciones por escenario

| Escenario | Ubicación final del stock |
|---|---|
| Recepción completa Línea | TIENDA/Existencias |
| Recepción completa Herido | TIENDA/Heridos |
| Recepción Tolerable (variante) | TIENDA/Existencias |
| Rechazo por daño | ALM/Revisión-Dañados (→ acta momento 2) |
| Rechazo por discrepancia Línea | ALM/Existencias |
| Rechazo por discrepancia Herido | ALM/Heridos |
| Tolerable detectado en tienda | TIENDA/Existencias (variante cambia a Tolerable) |
| Surtido cancelado | Regresa a origen original |
| En camión (tránsito) | Virtual/Tránsito Surtido |

---

## Configuración: motivos de retorno personalizados

Inventario → Configuración → Motivos de Retorno

Tabla editable con motivos precargados. Para agregar uno nuevo:
- Nombre, Tipo (Daño o Discrepancia), Secuencia.
- Los motivos de tipo **Daño** solo aparecen al seleccionar "Daño en tránsito" en el wizard.
- Los motivos de tipo **Discrepancia** solo aparecen al seleccionar "Discrepancia de surtido".
