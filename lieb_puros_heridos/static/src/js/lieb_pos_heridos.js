import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { _t } from "@web/core/l10n/translation";

patch(ProductScreen.prototype, {
    async addProductToOrder(product) {
        await super.addProductToOrder(...arguments);

        const order = this.pos.get_order?.() || this.pos.selectedOrder;
        if (!order) return;
        const line = order.get_selected_orderline?.() || order.selected_orderline;
        if (!line) return;
        const addedProduct = line.product || line.get_product?.();

        if (
            addedProduct?.lieb_condicion &&
            addedProduct.lieb_condicion !== "Línea" &&
            addedProduct.lieb_herido_qty <= 0
        ) {
            order.removeOrderline(line);
            this.env.services.notification.add(
                _t("Sin stock: %(name)s — No disponible en tienda.", { name: addedProduct.display_name }),
                { type: "danger", sticky: true }
            );
        }
    },
});
