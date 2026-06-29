from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class WizardRechazoTienda(models.TransientModel):
    _name = 'wizard.rechazo.tienda'
    _description = 'Rechazo de Piezas en Recepción de Tienda'

    picking_id = fields.Many2one('stock.picking', required=True, readonly=True)
    tipo_rechazo = fields.Selection([
        ('dano', 'Daño en tránsito'),
        ('discrepancia', 'Discrepancia de surtido'),
    ], string='Tipo de Rechazo', required=True)
    line_ids = fields.One2many(
        'wizard.rechazo.tienda.line',
        'wizard_id',
        string='Piezas a Rechazar',
    )

    @api.onchange('picking_id')
    def _onchange_picking_id(self):
        if self.picking_id:
            self.line_ids = [(5,)] + [(0, 0, {
                'move_id': move.id,
                'product_id': move.product_id.id,
                'qty_disponible': move.product_uom_qty,
                'qty_rechazada': 0.0,
            }) for move in self.picking_id.move_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')
            )]

    @api.onchange('tipo_rechazo')
    def _onchange_tipo_rechazo(self):
        for line in self.line_ids:
            line.motivo_retorno_id = False

    def action_confirmar(self):
        self.ensure_one()

        lines_con_rechazo = self.line_ids.filtered(lambda l: l.qty_rechazada > 0)
        if not lines_con_rechazo:
            raise UserError(_('Ingrese al menos una cantidad a rechazar.'))

        for line in lines_con_rechazo:
            if not line.motivo_retorno_id:
                raise ValidationError(_(
                    'El motivo de rechazo es obligatorio para "%s".'
                ) % line.product_id.display_name)
            if line.qty_rechazada > line.qty_disponible:
                raise ValidationError(_(
                    'La cantidad a rechazar (%s) supera la disponible (%s) en "%s".'
                ) % (line.qty_rechazada, line.qty_disponible, line.product_id.display_name))

        company = self.env.company
        loc_transit = self.env.ref('lieb_puros_heridos.location_transit_surtido')
        loc_revision = self.env.ref('lieb_puros_heridos.location_alm_revision_danados')
        loc_heridos = self.env.ref('lieb_puros_heridos.location_alm_heridos')

        int_type = self.env['stock.picking.type'].search(
            [('code', '=', 'internal'), ('company_id', '=', company.id)], limit=1
        ) or self.env['stock.picking.type'].search([('code', '=', 'internal')], limit=1)

        for line in lines_con_rechazo:
            condicion = line.product_id.lieb_condicion or ''
            if self.tipo_rechazo == 'dano':
                loc_dest_return = loc_revision
            else:
                # Discrepancia: vuelve al origen original según condición
                if condicion in ('Herido 20%', 'Herido 40%', 'Tolerable'):
                    loc_dest_return = loc_heridos
                else:
                    # Buscar el warehouse src del picking vía surtido
                    surtido = self.env['surtido.tienda'].search([
                        ('picking_in_ids', 'in', self.picking_id.ids),
                    ], limit=1)
                    loc_dest_return = (
                        surtido.warehouse_src_id.lot_stock_id
                        if surtido else loc_revision
                    )

            return_picking = self.env['stock.picking'].create({
                'picking_type_id': int_type.id,
                'location_id': loc_transit.id,
                'location_dest_id': loc_dest_return.id,
                'origin': self.picking_id.origin or self.picking_id.name,
                'company_id': company.id,
                'move_ids': [(0, 0, {
                    'name': _('Rechazo: %s') % line.product_id.display_name,
                    'product_id': line.product_id.id,
                    'product_uom': line.product_id.uom_id.id,
                    'product_uom_qty': line.qty_rechazada,
                    'location_id': loc_transit.id,
                    'location_dest_id': loc_dest_return.id,
                    'company_id': company.id,
                    'motivo_retorno_id': line.motivo_retorno_id.id,
                    'nota_rechazo': line.nota,
                })],
            })
            return_picking.action_confirm()
            return_picking.action_assign()
            return_picking.move_line_ids.filtered(lambda ml: not ml.company_id).write(
                {'company_id': company.id}
            )

            if not return_picking.move_line_ids:
                self.env['stock.move.line'].create({
                    'picking_id': return_picking.id,
                    'move_id': return_picking.move_ids[0].id,
                    'product_id': line.product_id.id,
                    'product_uom_id': line.product_id.uom_id.id,
                    'quantity': line.qty_rechazada,
                    'location_id': loc_transit.id,
                    'location_dest_id': loc_dest_return.id,
                    'company_id': return_picking.company_id.id,
                })
            # El almacén valida manualmente cuando recibe físicamente las piezas

            # Reducir qty del move original en el picking_in
            original_move = line.move_id
            new_qty = original_move.product_uom_qty - line.qty_rechazada
            if new_qty <= 0:
                original_move._action_cancel()
            else:
                original_move.product_uom_qty = new_qty
                if original_move.move_line_ids:
                    for ml in original_move.move_line_ids:
                        ml.quantity = new_qty

        tipo_label = dict(self._fields['tipo_rechazo'].selection)[self.tipo_rechazo]
        self.picking_id.message_post(
            body=_('Rechazo registrado (%s). %d línea(s) afectada(s).') % (
                tipo_label, len(lines_con_rechazo)
            )
        )
        return {'type': 'ir.actions.act_window_close'}


class WizardRechazoTiendaLine(models.TransientModel):
    _name = 'wizard.rechazo.tienda.line'
    _description = 'Línea de Rechazo'

    wizard_id = fields.Many2one('wizard.rechazo.tienda', ondelete='cascade')
    move_id = fields.Many2one('stock.move', readonly=True)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    condicion = fields.Char(related='product_id.lieb_condicion', readonly=True)
    qty_disponible = fields.Float(string='Cantidad en Picking', readonly=True, digits=(12, 2))
    qty_rechazada = fields.Float(string='Cantidad a Rechazar', digits=(12, 2))
    motivo_retorno_id = fields.Many2one(
        'motivo.retorno',
        string='Motivo',
        domain="[('tipo', '=', parent.tipo_rechazo)]",
    )
    nota = fields.Text(string='Nota')
