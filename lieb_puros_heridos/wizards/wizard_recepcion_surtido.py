from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class WizardRecepcionSurtido(models.TransientModel):
    _name = 'wizard.recepcion.surtido'
    _description = 'Recepción con Revisión de Surtido'

    surtido_id = fields.Many2one('surtido.tienda', required=True, readonly=True)
    line_ids = fields.One2many(
        'wizard.recepcion.surtido.line',
        'wizard_id',
        string='Líneas',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        surtido_id = self.env.context.get('default_surtido_id')
        if not surtido_id:
            return res
        surtido = self.env['surtido.tienda'].browse(surtido_id)
        lines = []
        for picking in surtido.picking_in_ids.filtered(
            lambda p: p.state not in ('done', 'cancel')
        ):
            for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                lines.append((0, 0, {
                    'picking_id': picking.id,
                    'move_id': move.id,
                    'product_id': move.product_id.id,
                    'qty_esperada': move.product_uom_qty,
                    'qty_recibida': move.product_uom_qty,
                }))
        res['line_ids'] = lines
        return res

    def action_confirmar(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('No hay líneas para procesar.'))

        # Construir mapa product_id → wizard_line (no confiar en move_id/picking_id
        # del wizard porque web_save no siempre envía campos readonly del One2many)
        line_by_product = {}
        for line in self.line_ids:
            if line.product_id:
                line_by_product[line.product_id.id] = line

        company = self.env.company
        loc_transit = self.env.ref('lieb_puros_heridos.location_transit_surtido')
        loc_revision = self.env.ref('lieb_puros_heridos.location_alm_revision_danados')
        loc_heridos = self.env.ref('lieb_puros_heridos.location_alm_heridos')
        int_type = self.env['stock.picking.type'].search(
            [('code', '=', 'internal'), ('company_id', '=', company.id)], limit=1
        ) or self.env['stock.picking.type'].search([('code', '=', 'internal')], limit=1)

        # Validar cantidades antes de procesar
        for pid, line in line_by_product.items():
            if line.qty_recibida < 0:
                raise ValidationError(_(
                    'Cantidad recibida no puede ser negativa: %s'
                ) % line.product_id.display_name)
            move = self.surtido_id.picking_in_ids.mapped('move_ids').filtered(
                lambda m: m.product_id.id == pid and m.state not in ('done', 'cancel')
            )[:1]
            if move and line.qty_recibida > move.product_uom_qty:
                raise ValidationError(_(
                    'Cantidad recibida (%s) supera la esperada (%s) en "%s".'
                ) % (line.qty_recibida, move.product_uom_qty, line.product_id.display_name))
            qty_rechazada = (move.product_uom_qty if move else 0) - line.qty_recibida
            if qty_rechazada > 0 and not line.motivo_retorno_id:
                raise ValidationError(_(
                    'El motivo de rechazo es obligatorio para "%s" (hay %s piezas rechazadas).'
                ) % (line.product_id.display_name, qty_rechazada))

        # Procesar cada IN picking directamente desde el surtido
        pending_pickings = self.surtido_id.picking_in_ids.filtered(
            lambda p: p.state not in ('done', 'cancel')
        )

        for picking in pending_pickings:
            for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                wline = line_by_product.get(move.product_id.id)
                qty_recibida = wline.qty_recibida if wline else move.product_uom_qty

                if qty_recibida > 0:
                    move.product_uom_qty = qty_recibida
                    if move.move_line_ids:
                        move.move_line_ids.write({'quantity': qty_recibida})
                    else:
                        self.env['stock.move.line'].create({
                            'picking_id': picking.id,
                            'move_id': move.id,
                            'product_id': move.product_id.id,
                            'product_uom_id': move.product_uom.id,
                            'quantity': qty_recibida,
                            'location_id': move.location_id.id,
                            'location_dest_id': move.location_dest_id.id,
                            'company_id': picking.company_id.id,
                        })
                else:
                    move._action_cancel()

            active_moves = picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
            if active_moves:
                picking.with_context(skip_backorder=True, skip_immediate=True).button_validate()

            # Retornos para rechazos
            for move in picking.move_ids:
                wline = line_by_product.get(move.product_id.id)
                if not wline:
                    continue
                qty_original = move.product_uom_qty + (
                    move.product_uom_qty - (wline.qty_recibida or move.product_uom_qty)
                )
                qty_rechazada = (move.product_uom_qty - wline.qty_recibida) \
                    if wline.qty_recibida < move.product_uom_qty else 0
                # Calcular rechazado como lo que el usuario dejó de recibir
                expected = self.line_ids.filtered(
                    lambda l: l.product_id.id == move.product_id.id
                )[:1]
                qty_rechazada = max(0.0, (expected.qty_esperada - expected.qty_recibida)
                                   if expected else 0.0)
                if qty_rechazada <= 0:
                    continue

                condicion = move.product_id.lieb_condicion or ''
                if wline.tipo_rechazo == 'dano':
                    loc_dest_return = loc_revision
                else:
                    loc_dest_return = loc_heridos if condicion in (
                        'Herido 20%', 'Herido 40%', 'Tolerable'
                    ) else (self.surtido_id.warehouse_src_id.lot_stock_id or loc_revision)

                return_picking = self.env['stock.picking'].create({
                    'picking_type_id': int_type.id,
                    'location_id': loc_transit.id,
                    'location_dest_id': loc_dest_return.id,
                    'origin': self.surtido_id.name,
                    'company_id': company.id,
                })
                self.env['stock.move'].create({
                    'name': _('Rechazo: %s') % move.product_id.display_name,
                    'picking_id': return_picking.id,
                    'product_id': move.product_id.id,
                    'product_uom': move.product_uom.id,
                    'product_uom_qty': qty_rechazada,
                    'location_id': loc_transit.id,
                    'location_dest_id': loc_dest_return.id,
                    'motivo_retorno_id': wline.motivo_retorno_id.id,
                    'nota_rechazo': wline.nota,
                })
                return_picking.action_confirm()
                return_picking.action_assign()

        self.surtido_id.action_check_received()
        self.surtido_id.message_post(body=_('Recepción con revisión completada.'))
        return {'type': 'ir.actions.act_window_close'}


class WizardRecepcionSurtidoLine(models.TransientModel):
    _name = 'wizard.recepcion.surtido.line'
    _description = 'Línea de Recepción con Revisión'

    wizard_id = fields.Many2one('wizard.recepcion.surtido', ondelete='cascade')
    picking_id = fields.Many2one('stock.picking', readonly=True)
    move_id = fields.Many2one('stock.move', readonly=True)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    condicion = fields.Char(related='product_id.lieb_condicion', readonly=True, string='Condición')
    qty_esperada = fields.Float(string='Esperada', readonly=True, digits=(12, 2))
    qty_recibida = fields.Float(string='Recibida', digits=(12, 2))
    qty_rechazada = fields.Float(
        string='Rechazada',
        compute='_compute_qty_rechazada',
        digits=(12, 2),
    )
    tipo_rechazo = fields.Selection([
        ('dano', 'Daño'),
        ('discrepancia', 'Discrepancia'),
    ], string='Tipo Rechazo')
    motivo_retorno_id = fields.Many2one(
        'motivo.retorno',
        string='Motivo',
        domain="[('tipo', '=', tipo_rechazo)]",
    )
    nota = fields.Text(string='Nota')

    @api.depends('qty_esperada', 'qty_recibida')
    def _compute_qty_rechazada(self):
        for line in self:
            line.qty_rechazada = max(0.0, line.qty_esperada - line.qty_recibida)
