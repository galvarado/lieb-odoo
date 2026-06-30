# Spec: Programa Friends & Family — Validación QR en POS

## Objetivo

Permitir que clientes registrados como "Friends & Family" (F&F) apliquen un descuento
en punto de venta mediante un QR temporal enviado a su celular al momento de la compra.
El cajero nunca ve el código para evitar uso indebido.

---

## Flujo completo

1. **Admin registra cliente F&F** en el backend de Odoo (`res.partner`)
   - Activa checkbox `es_friends_family`
   - Sistema genera automáticamente un `ff_secret` (UUID v4) almacenado de forma oculta
   - El secreto nunca se muestra en ninguna pantalla

2. **En el momento de la compra (POS)**
   - Cajero busca y selecciona al cliente en el POS
   - Pulsa botón **"Enviar código F&F"**
   - Sistema genera un **token temporal** (derivado del secreto, válido 10 minutos, un solo uso)
   - Token se convierte en QR y se envía al número de celular registrado del cliente (SMS o WhatsApp)

3. **Validación**
   - Cliente muestra el QR en su celular
   - Cajero escanea el QR con lector de código de barras conectado al POS
   - POS llama a endpoint `POST /ff/validate` con el token escaneado
   - Endpoint verifica: token válido + no usado + no expirado + pertenece al cliente seleccionado
   - Si válido → aplica descuento F&F y marca token como usado
   - Si inválido → muestra error, no aplica descuento

4. **Descuento aplicado**
   - Puede ser pricelist exclusiva F&F o porcentaje fijo configurable por admin
   - Se registra en el pedido POS como línea de descuento con etiqueta "F&F"

---

## Seguridad

| Riesgo | Mitigación |
|--------|-----------|
| Cajero copia el código | `ff_secret` tiene `groups="base.group_system"` — invisible en toda UI |
| Screenshot reutilizable | Token temporal: 10 min de vigencia, un solo uso por transacción |
| Alguien adivina el token | UUID v4 + HMAC-SHA256 con secreto del partner — espacio de 2^128 |
| Token interceptado en tránsito | Enviado directo al celular del cliente, no pasa por el cajero |
| Compartir el QR con terceros | Token vinculado al `partner_id` seleccionado en el POS — si no coincide, inválido |

---

## Componentes técnicos

### Backend (`res.partner`)

```python
es_friends_family = fields.Boolean(string='Friends & Family', default=False)
ff_secret = fields.Char(
    string='Secreto F&F',
    copy=False,
    groups='base.group_system',  # solo superadmin
)
ff_discount = fields.Float(string='Descuento F&F (%)', default=15.0)
```

### Token temporal (`ff.token` — modelo transitorio o tabla simple)

```
ff_token (Char, unique)   — HMAC del secreto + timestamp + nonce
partner_id (Many2one)
expires_at (Datetime)     — now + 10 min
used (Boolean)
pos_session_id (Many2one) — opcional, para auditoría
```

### Controller HTTP

```
POST /ff/validate
  Body: { token: "...", partner_id: 123 }
  Response: { valid: true, discount: 15.0 }
           | { valid: false, reason: "expired|used|mismatch" }
```

El endpoint nunca devuelve el secreto ni el token en claro en la respuesta.

### Widget POS (JavaScript / OWL)

- Botón "Enviar código F&F" visible solo si cliente seleccionado tiene `es_friends_family=True`
- Al pulsar: llama RPC `action_send_ff_token(partner_id)` → backend genera token, envía SMS
- Campo de escaneo QR: input oculto que captura el scan del lector físico
- Al recibir scan: llama `/ff/validate` → si ok, aplica descuento vía `order.addDiscount()`

### Envío SMS/WhatsApp

- **Opción A**: Odoo IAP SMS (sin configuración extra, pago por crédito)
- **Opción B**: Twilio (más barato en volumen, requiere cuenta y webhook)
- **Opción C**: WhatsApp Business API (mejor UX, más complejo de configurar)

---

## Módulo sugerido

Módulo separado: `lieb_friends_family`
- Depende de: `point_of_sale`, `sms`, `contacts`
- No mezclar con `lieb_puros_heridos`

---

## Configuración admin

- Activar/desactivar programa F&F globalmente
- Porcentaje de descuento por defecto (override por cliente)
- Canal de envío: SMS / WhatsApp / Email
- Vigencia del token (default: 10 min)
- Pricelist F&F opcional (alternativa al porcentaje fijo)

---

## Pendientes a definir antes de implementar

- [ ] ¿Proveedor SMS? (IAP Odoo vs Twilio vs WhatsApp)
- [ ] ¿Descuento fijo (%) o pricelist completa?
- [ ] ¿Un descuento por visita o ilimitado?
- [ ] ¿Auditoría de usos por cliente? (historial de compras F&F)
- [ ] ¿Fecha de vencimiento de membresía F&F?
- [ ] ¿El cliente puede inscribir a otras personas? ¿Hay límite?
