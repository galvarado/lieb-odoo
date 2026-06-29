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
            if vals.get('company_id'):
                continue
            if vals.get('move_id'):
                move = self.env['stock.move'].browse(vals['move_id'])
                company = move.company_id or (move.picking_id.company_id if move.picking_id else None)
            elif vals.get('picking_id'):
                picking = self.env['stock.picking'].browse(vals['picking_id'])
                company = picking.company_id
            else:
                company = None
            vals['company_id'] = (company.id if company else None) or self.env.company.id
        return super().create(vals_list)
