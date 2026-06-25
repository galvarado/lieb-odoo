from odoo import _, api, models
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def _process_order(self, order, existing_order):
        condicion_attr = self.env.ref(
            'lieb_puros_heridos.product_attribute_condicion',
            raise_if_not_found=False,
        )
        if condicion_attr:
            session_id = order.get('pos_session_id') or order.get('session_id')
            session = self.env['pos.session'].browse(session_id)
            location = session.config_id.picking_type_id.default_location_src_id
            for line in order.get('lines', []):
                vals = line[2] if isinstance(line, (list, tuple)) else line
                product_id = vals.get('product_id')
                if not product_id:
                    continue
                product = self.env['product.product'].browse(product_id)
                for ptav in product.product_template_attribute_value_ids:
                    if ptav.attribute_id == condicion_attr:
                        if ptav.product_attribute_value_id.name != 'Línea':
                            qty = product.with_context(location=location.id).qty_available
                            if qty <= 0:
                                raise UserError(_(
                                    'Sin stock de herido: %(name)s — No se puede vender.',
                                    name=product.display_name,
                                ))
                        break
        return super()._process_order(order, existing_order)
