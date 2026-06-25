from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    lieb_condicion = fields.Char(
        string='Condición Herido',
        compute='_compute_lieb_condicion',
        store=True,
    )

    lieb_herido_qty = fields.Float(
        string='Stock Herido POS',
        digits=(16, 2),
        default=0.0,
    )

    lieb_condicion_discount = fields.Float(
        string='Descuento Condición %',
        compute='_compute_lieb_condicion_discount',
        digits=(5, 2),
    )

    @api.depends(
        'product_template_attribute_value_ids',
        'product_template_attribute_value_ids.product_attribute_value_id',
    )
    def _compute_lieb_condicion(self):
        condicion_attr = self.env.ref(
            'lieb_puros_heridos.product_attribute_condicion',
            raise_if_not_found=False,
        )
        for product in self:
            val = None
            if condicion_attr:
                for ptav in product.product_template_attribute_value_ids:
                    if ptav.attribute_id == condicion_attr:
                        val = ptav.product_attribute_value_id.name
                        break
            product.lieb_condicion = val

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

    @api.model
    def _load_pos_data_fields(self, config_id):
        result = super()._load_pos_data_fields(config_id)
        for f in ('lieb_condicion', 'lieb_herido_qty'):
            if f not in result:
                result.append(f)
        return result

    @api.model
    def _load_pos_data(self, data):
        result = super()._load_pos_data(data)
        condicion_attr = self.env.ref(
            'lieb_puros_heridos.product_attribute_condicion',
            raise_if_not_found=False,
        )
        if not condicion_attr:
            return result
        session = self.env['pos.session'].search([
            ('state', 'in', ['opening_control', 'opened']),
            ('user_id', '=', self.env.uid),
        ], limit=1)
        location = (
            session.config_id.picking_type_id.default_location_src_id
            if session else None
        )
        for product_data in result.get('data', []):
            product = self.browse(product_data['id'])
            # Descuento en lst_price para POS
            discount = product.lieb_condicion_discount
            if discount:
                product_data['lst_price'] = product_data['lst_price'] * (1 - discount / 100.0)
            # Sobreescribir lieb_herido_qty con stock real en ubicación de la tienda
            condicion = product_data.get('lieb_condicion')
            if condicion and condicion != 'Línea' and location:
                product_data['lieb_herido_qty'] = product.with_context(
                    location=location.id
                ).qty_available
        return result
