from odoo.tests import TransactionCase


class TestDiscountPercent(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.attr_condicion = cls.env.ref('lieb_puros_heridos.product_attribute_condicion')
        cls.val_linea = cls.env.ref('lieb_puros_heridos.product_attribute_value_linea')
        cls.val_herido_20 = cls.env.ref('lieb_puros_heridos.product_attribute_value_herido_20')
        cls.val_herido_40 = cls.env.ref('lieb_puros_heridos.product_attribute_value_herido_40')
        cls.val_herido_20.discount_percent = 20.0
        cls.val_herido_40.discount_percent = 40.0

    def test_linea_discount_is_zero(self):
        self.assertEqual(self.val_linea.discount_percent, 0.0)

    def test_herido_20_discount(self):
        self.assertEqual(self.val_herido_20.discount_percent, 20.0)

    def test_herido_40_discount(self):
        self.assertEqual(self.val_herido_40.discount_percent, 40.0)

    def test_computed_discount_on_product(self):
        template = self.env['product.template'].create({
            'name': 'Test Puro Descuento',
            'type': 'consu',
            'list_price': 100.0,
            'attribute_line_ids': [(0, 0, {
                'attribute_id': self.attr_condicion.id,
                'value_ids': [
                    (4, self.val_linea.id),
                    (4, self.val_herido_20.id),
                ],
            })],
        })
        # Activar variantes dinámicas para el test
        ptavs = self.env['product.template.attribute.value'].search([
            ('product_tmpl_id', '=', template.id),
        ])
        ptavs.write({'ptav_active': True})
        template._create_variant_ids()

        herido_20 = template.product_variant_ids.filtered(
            lambda v: any(
                ptav.product_attribute_value_id == self.val_herido_20
                for ptav in v.product_template_attribute_value_ids
            )
        )
        linea = template.product_variant_ids.filtered(
            lambda v: any(
                ptav.product_attribute_value_id == self.val_linea
                for ptav in v.product_template_attribute_value_ids
            )
        )
        self.assertEqual(herido_20.lieb_condicion_discount, 20.0)
        self.assertEqual(linea.lieb_condicion_discount, 0.0)

    def test_precio_herido_es_precio_base_menos_descuento(self):
        self.assertAlmostEqual(
            100.0 * (1 - self.val_herido_20.discount_percent / 100.0),
            80.0,
        )
        self.assertAlmostEqual(
            100.0 * (1 - self.val_herido_40.discount_percent / 100.0),
            60.0,
        )
