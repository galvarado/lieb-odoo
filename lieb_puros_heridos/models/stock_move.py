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
            move = self.env['stock.move'].browse(vals['move_id']) if vals.get('move_id') else None
            picking = self.env['stock.picking'].browse(vals['picking_id']) if vals.get('picking_id') else None

            # company_id
            if not vals.get('company_id'):
                company = (
                    (move.company_id if move else None)
                    or (picking.company_id if picking else None)
                    or self.env.company
                )
                vals['company_id'] = company.id

            # product_uom_id
            if not vals.get('product_uom_id'):
                uom = None
                if move:
                    uom = (
                        move.product_uom
                        or getattr(move, 'product_uom_id', None)
                        or (move.product_id.uom_id if move.product_id else None)
                    )
                if not uom and vals.get('product_id'):
                    product = self.env['product.product'].browse(vals['product_id'])
                    uom = product.uom_id
                if uom:
                    vals['product_uom_id'] = uom.id

        return super().create(vals_list)
