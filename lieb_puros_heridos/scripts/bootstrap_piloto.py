"""
Bootstrap de la tienda piloto para la validación manual de Fase 1.

Hace tres cosas:
  1. Crea (o verifica) el warehouse de la tienda piloto.
  2. Reasigna la ubicación TIENDA/Heridos (location_tienda_piloto_heridos)
     al stock de la tienda recién creada.
  3. Coloca stock de prueba de la variante Línea en la tienda piloto.

Uso:
    python3 bootstrap_piloto.py \
        --url https://<db>.odoo.com \
        --db <db_name> \
        --apikey <api_key> \
        --tienda "Tienda Centro" \
        --codigo TCTR \
        --producto "Cohiba Siglo I Línea" \
        --cantidad 10
"""

import argparse
import sys
import xmlrpc.client


TIENDA_HERIDOS_XMLID = "lieb_puros_heridos.location_tienda_piloto_heridos"
CONDICION_LINEA_XMLID = "lieb_puros_heridos.product_attribute_value_linea"


def connect(url, db, apikey):
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, "__api__", apikey, {})
    if not uid:
        sys.exit("Autenticación fallida.")
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
    return uid, models


def call(models, db, uid, apikey, model, method, args, kwargs=None):
    return models.execute_kw(db, uid, apikey, model, method, args, kwargs or {})


def resolve_xmlid(models, db, uid, apikey, xmlid):
    module, name = xmlid.split(".")
    result = call(models, db, uid, apikey, "ir.model.data", "search_read",
                  [[["module", "=", module], ["name", "=", name]]],
                  {"fields": ["res_id"], "limit": 1})
    if not result:
        sys.exit(f"XML ID no encontrado: {xmlid}")
    return result[0]["res_id"]


def get_or_create_warehouse(models, db, uid, apikey, nombre, codigo):
    existing = call(models, db, uid, apikey, "stock.warehouse", "search_read",
                    [[["code", "=", codigo]]],
                    {"fields": ["id", "name", "lot_stock_id"], "limit": 1})
    if existing:
        wh = existing[0]
        print(f"Warehouse ya existe: {wh['name']} (id={wh['id']})")
        return wh["id"], wh["lot_stock_id"][0]

    wh_id = call(models, db, uid, apikey, "stock.warehouse", "create",
                 [{"name": nombre, "code": codigo}])
    wh = call(models, db, uid, apikey, "stock.warehouse", "read",
              [[wh_id]], {"fields": ["lot_stock_id"]})[0]
    print(f"Warehouse creado: {nombre} (id={wh_id})")
    return wh_id, wh["lot_stock_id"][0]


def reasignar_tienda_heridos(models, db, uid, apikey, stock_location_id):
    loc_id = resolve_xmlid(models, db, uid, apikey, TIENDA_HERIDOS_XMLID)
    call(models, db, uid, apikey, "stock.location", "write",
         [[loc_id], {"location_id": stock_location_id}])
    print(f"TIENDA/Heridos reasignada al stock de la tienda (location_id={stock_location_id})")
    return loc_id


def buscar_variante_linea(models, db, uid, apikey, nombre_producto):
    valor_linea_id = resolve_xmlid(models, db, uid, apikey, CONDICION_LINEA_XMLID)

    templates = call(models, db, uid, apikey, "product.template", "search_read",
                     [[["name", "ilike", nombre_producto]]],
                     {"fields": ["id", "name", "product_variant_ids"], "limit": 5})
    if not templates:
        sys.exit(f"No se encontró ningún producto con nombre '{nombre_producto}'.")

    print(f"Productos encontrados: {[t['name'] for t in templates]}")
    template = templates[0]

    for variant_id in template["product_variant_ids"]:
        variant = call(models, db, uid, apikey, "product.product", "read",
                       [[variant_id]],
                       {"fields": ["id", "display_name", "product_template_attribute_value_ids"]})[0]

        attr_values = call(models, db, uid, apikey,
                           "product.template.attribute.value", "read",
                           [variant["product_template_attribute_value_ids"]],
                           {"fields": ["product_attribute_value_id"]})

        value_ids = [av["product_attribute_value_id"][0] for av in attr_values]
        if valor_linea_id in value_ids:
            print(f"Variante Línea encontrada: {variant['display_name']} (id={variant['id']})")
            return variant["id"]

    sys.exit("No se encontró la variante Línea del producto especificado.")


def colocar_stock(models, db, uid, apikey, product_id, location_id, cantidad):
    quant_id = call(models, db, uid, apikey, "stock.quant", "create", [{
        "product_id": product_id,
        "location_id": location_id,
        "inventory_quantity": cantidad,
    }])
    call(models, db, uid, apikey, "stock.quant", "action_apply_inventory", [[quant_id]])
    print(f"Stock de prueba aplicado: {cantidad} unidades en location_id={location_id}")


def main():
    parser = argparse.ArgumentParser(description="Bootstrap tienda piloto Fase 1")
    parser.add_argument("--url", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--apikey", required=True)
    parser.add_argument("--tienda", required=True, help="Nombre de la tienda piloto")
    parser.add_argument("--codigo", required=True, help="Código del warehouse (ej: TCTR)")
    parser.add_argument("--producto", required=True, help="Nombre del producto para stock de prueba")
    parser.add_argument("--cantidad", type=int, default=10, help="Unidades de stock de prueba (default: 10)")
    args = parser.parse_args()

    uid, models = connect(args.url, args.db, args.apikey)

    print("\n[1/4] Warehouse de la tienda piloto")
    _wh_id, stock_loc_id = get_or_create_warehouse(models, args.db, uid, args.apikey,
                                                    args.tienda, args.codigo)

    print("\n[2/4] Reasignar TIENDA/Heridos")
    reasignar_tienda_heridos(models, args.db, uid, args.apikey, stock_loc_id)

    print("\n[3/4] Buscar variante Línea del producto de prueba")
    variant_id = buscar_variante_linea(models, args.db, uid, args.apikey, args.producto)

    print("\n[4/4] Colocar stock de prueba")
    colocar_stock(models, args.db, uid, args.apikey, variant_id, stock_loc_id, args.cantidad)

    print("\nBootstrap completado. El recorrido manual de Fase 1 puede comenzar.")


if __name__ == "__main__":
    main()
