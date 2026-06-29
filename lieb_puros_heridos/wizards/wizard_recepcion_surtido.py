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

        for line in self.line_ids:
            if not line.product_id or not line.move_id:
                continue
            if line.qty_recibida < 0:
                raise ValidationError(_(
                    'Cantidad recibida no puede ser negativa: %s'
                ) % line.product_id.display_name)
            if line.qty_recibida > line.qty_esperada:
                raise ValidationError(_(
                    'Cantidad recibida (%s) supera la esperada (%s) en "%s".'
                ) % (line.qty_recibida, line.qty_esperada, line.product_id.display_name))
            qty_rechazada = line.qty_esperada - line.qty_recibida
            if qty_rechazada > 0 and not line.motivo_retorno_id:
                raise ValidationError(_(
                    'El motivo de rechazo es obligatorio para "%s" (hay %s piezas rechazadas).'
                ) % (line.product_id.display_name, qty_rechazada))

        # Agrupar líneas por picking
        pickings_lines = {}
        for line in self.line_ids:
            pickings_lines.setdefault(line.picking_id.id, []).append(line)

        loc_transit = self.env.ref('lieb_puros_heridos.location_transit_surtido')
        loc_revision = self.env.ref('lieb_puros_heridos.location_alm_revision_danados')
        loc_heridos = self.env.ref('lieb_puros_heridos.location_alm_heridos')
        int_type = self.env['stock.picking.type'].search(
            [('code', '=', 'internal')], limit=1
        )

        for picking_id, lines in pickings_lines.items():
            picking = self.env['stock.picking'].browse(picking_id)

            # Setear cantidades recibidas en move lines
            for line in lines:
                move = line.move_id
                if line.qty_recibida > 0:
                    move.product_uom_qty = line.qty_recibida
                    if move.move_line_ids:
                        move.move_line_ids.write({'quantity': line.qty_recibida})
                    else:
                        self.env['stock.move.line'].create({
                            'picking_id': picking.id,
                            'move_id': move.id,
                            'product_id': move.product_id.id,
                            'product_uom_id': move.product_uom.id,
                            'quantity': line.qty_recibida,
                            'location_id': move.location_id.id,
                            'location_dest_id': move.location_dest_id.id,
                        })
                else:
                    # Nada recibido de este move — cancelar
                    move._action_cancel()

            # Validar picking si aún tiene moves activos
            active_moves = picking.move_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')
            )
            if active_moves:
                picking.with_context(
                    skip_backorder=True, skip_immediate=True
                ).button_validate()

            # Crear retornos para cantidades rechazadas
            for line in lines:
                qty_rechazada = line.qty_esperada - line.qty_recibida
                if qty_rechazada <= 0:
                    continue

                condicion = line.product_id.lieb_condicion or ''
                if line.tipo_rechazo == 'dano':
                    loc_dest_return = loc_revision
                else:
                    if condicion in ('Herido 20%', 'Herido 40%', 'Tolerable'):
                        loc_dest_return = loc_heridos
                    else:
                        loc_dest_return = (
                            self.surtido_id.warehouse_src_id.lot_stock_id
                            if self.surtido_id.warehouse_src_id else loc_revision
                        )

                return_picking = self.env['stock.picking'].create({
                    'picking_type_id': int_type.id,
                    'location_id': loc_transit.id,
                    'location_dest_id': loc_dest_return.id,
                    'origin': self.surtido_id.name,
                    'move_ids': [(0, 0, {
                        'name': _('Rechazo: %s') % line.product_id.display_name,
                        'product_id': line.product_id.id,
                        'product_uom': line.product_id.uom_id.id,
                        'product_uom_qty': qty_rechazada,
                        'location_id': loc_transit.id,
                        'location_dest_id': loc_dest_return.id,
                        'motivo_retorno_id': line.motivo_retorno_id.id,
                        'nota_rechazo': line.nota,
                    })],
                })
                return_picking.action_confirm()
                return_picking.action_assign()
                if not return_picking.move_line_ids:
                    self.env['stock.move.line'].create({
                        'picking_id': return_picking.id,
                        'move_id': return_picking.move_ids[0].id,
                        'product_id': line.product_id.id,
                        'product_uom_id': line.product_id.uom_id.id,
                        'quantity': qty_rechazada,
                        'location_id': loc_transit.id,
                        'location_dest_id': loc_dest_return.id,
                    })
                # El almacén valida manualmente cuando recibe físicamente las piezas

        self.surtido_id.action_check_received()
        self.surtido_id.message_post(
            body=_('Recepción con revisión completada.')
        )
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
