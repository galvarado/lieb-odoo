from odoo import fields, models


class ProductAttributeValue(models.Model):
    _inherit = 'product.attribute.value'

    discount_percent = fields.Float(
        string='% de Descuento',
        digits=(5, 2),
        default=0.0,
    )
