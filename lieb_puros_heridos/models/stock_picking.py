from odoo import fields, models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    es_surtido_in = fields.Boolean(
        compute='_compute_es_surtido_in',
        store=False,
    )
    es_rechazo_surtido = fields.Boolean(
        string='Es Rechazo de Surtido',
        default=False,
        copy=False,
    )

    def _compute_es_surtido_in(self):
        surtido_in_ids = self.env['surtido.tienda'].search([]).picking_in_ids.ids
        for picking in self:
            picking.es_surtido_in = picking.id in surtido_in_ids

    def action_rechazar_piezas(self):
        self.ensure_one()
        if not self.es_surtido_in:
            raise UserError(_('Este picking no es una entrada de surtido a tienda.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Rechazar Piezas'),
            'res_model': 'wizard.rechazo.tienda',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_picking_id': self.id},
        }

    def action_registrar_tolerable(self):
        self.ensure_one()
        if not self.es_surtido_in:
            raise UserError(_('Este picking no es una entrada de surtido a tienda.'))
        if self.location_dest_id.usage != 'internal':
            raise UserError(_('La ubicación destino del picking no es interna.'))

        acta = self.env['acta.clasificacion'].create({
            'momento': '2',
            'es_simplificada': True,
            'ubicacion_id': self.location_dest_id.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Acta Tolerable – Tienda'),
            'res_model': 'acta.clasificacion',
            'res_id': acta.id,
            'view_mode': 'form',
        }
