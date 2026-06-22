/** @odoo-module **/
import { Component } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

class CondicionButtons extends Component {
    static template = "lieb_puros_heridos.CondicionButtons";
    static props = {};

    setup() {
        this.pos = usePos();
        this.notification = useService("notification");
    }

    get currentLine() {
        return this.pos.get_order()?.get_selected_orderline();
    }

    get isLinea() {
        const line = this.currentLine;
        if (!line) return false;
        return line.get_product().lieb_condicion === "Línea";
    }

    _tmplId(product) {
        const t = product.product_tmpl_id;
        return Array.isArray(t) ? t[0] : t;
    }

    _findSibling(condicion) {
        const currentProduct = this.currentLine?.get_product();
        if (!currentProduct) return null;
        const tmplId = this._tmplId(currentProduct);

        // Odoo 18 new model system
        const allProducts =
            this.pos.models?.["product.product"]?.getAll?.() ??
            Object.values(this.pos.db?.product_by_id ?? {});

        return (
            allProducts.find(
                (p) =>
                    this._tmplId(p) === tmplId &&
                    p.lieb_condicion === condicion
            ) ?? null
        );
    }

    applyCondicion(condicion) {
        const line = this.currentLine;
        if (!line) return;

        const sibling = this._findSibling(condicion);
        if (!sibling) {
            this.notification.add(
                `No hay variante "${condicion}" cargada para este puro. Abre una sesión nueva para recargar productos.`,
                { type: "warning" }
            );
            return;
        }

        const qty = line.get_quantity();
        const order = this.pos.get_order();
        order.remove_orderline(line);
        order.add_product(sibling, { quantity: qty });
    }
}

ProductScreen.components = {
    ...ProductScreen.components,
    CondicionButtons,
};
