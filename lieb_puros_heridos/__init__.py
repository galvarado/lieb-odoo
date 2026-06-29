from . import models
from . import wizards


def post_init_hook(env):
    warehouse = env['stock.warehouse'].search([('code', '=', 'TSF')], limit=1)
    if not warehouse:
        return
    view_loc = warehouse.view_location_id
    for xmlid in [
        'lieb_puros_heridos.location_alm_heridos',
        'lieb_puros_heridos.location_alm_revision_danados',
    ]:
        loc = env.ref(xmlid, raise_if_not_found=False)
        if loc:
            loc.location_id = view_loc
