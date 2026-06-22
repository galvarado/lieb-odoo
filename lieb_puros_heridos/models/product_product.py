from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    lieb_condicion_discount = fields.Float(
        string='Descuento Condición %',
        compute='_compute_lieb_condicion_discount',
        digits=(5, 2),
    )

    @api.depends(
        'product_template_attribute_value_ids',
        'product_template_attribute_value_ids.product_attribute_value_id.discount_percent',
    )
    def _compute_lieb_condicion_discount(self):
        condicion_attr = self.env.ref(
            'lieb_puros_heridos.product_attribute_condicion',
            raise_if_not_found=False,
        )
        for product in self:
            discount = 0.0
            if condicion_attr:
                for ptav in product.product_template_attribute_value_ids:
                    if ptav.attribute_id == condicion_attr:
                        discount = ptav.product_attribute_value_id.discount_percent
                        break
            product.lieb_condicion_discount = discount

    def _get_contextual_price(self, quantity=1.0):
        price = super()._get_contextual_price(quantity)
        discount = self.lieb_condicion_discount
        if discount:
            price = price * (1 - discount / 100.0)
        return price
