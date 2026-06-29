from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    motivo_retorno_id = fields.Many2one(
        'motivo.retorno',
        string='Motivo de Rechazo',
        ondelete='restrict',
    )
    nota_rechazo = fields.Text(string='Nota de Rechazo')
