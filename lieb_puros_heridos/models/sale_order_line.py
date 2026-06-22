from odoo import models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _get_display_price(self):
        price = super()._get_display_price()
        discount = self.product_id.lieb_condicion_discount
        if discount:
            price = price * (1 - discount / 100.0)
        return price
