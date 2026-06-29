from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    motivo_retorno_id = fields.Many2one(
        'motivo.retorno',
        string='Motivo de Rechazo',
        ondelete='restrict',
    )
    nota_rechazo = fields.Text(string='Nota de Rechazo')


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            move = None
            if vals.get('move_id'):
                move = self.env['stock.move'].browse(vals['move_id'])
            if not vals.get('company_id'):
                company = (move.company_id if move else None) or \
                    (self.env['stock.picking'].browse(vals['picking_id']).company_id
                     if vals.get('picking_id') else None)
                vals['company_id'] = (company.id if company else None) or self.env.company.id
            if not vals.get('product_uom_id') and move and move.product_uom:
                vals['product_uom_id'] = move.product_uom.id
        return super().create(vals_list)
