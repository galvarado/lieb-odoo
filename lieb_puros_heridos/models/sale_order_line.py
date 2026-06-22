from odoo import models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
