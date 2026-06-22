from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ActaClasificacion(models.Model):
    _name = 'acta.clasificacion'
    _description = 'Acta de Clasificación de Puros Heridos'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha desc, name desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Referencia',
        readonly=True,
        copy=False,
        default=lambda self: _('Nuevo'),
    )
    momento = fields.Selection([
        ('1', '1 – Importación'),
        ('2', '2 – Recepción en Tienda'),
        ('3', '3 – Daño con el Tiempo'),
    ], string='Momento de Identificación', required=True, tracking=True)
    fecha = fields.Date(
        string='Fecha',
        default=fields.Date.today,
        required=True,
    )
    ubicacion_id = fields.Many2one(
        'stock.location',
        string='Ubicación Origen',
        domain=[('usage', '=', 'internal')],
        required=True,
        tracking=True,
        default=lambda self: self.env.ref(
            'lieb_puros_heridos.location_alm_revision_danados',
            raise_if_not_found=False,
        ),
    )
    responsable_ids = fields.Many2many(
        'res.users',
        'acta_clasificacion_responsable_rel',
        'acta_id',
        'user_id',
        string='Responsables',
    )
    firma_encargada = fields.Binary(string='Firma')
    observaciones = fields.Text(string='Observaciones')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Validada'),
    ], default='draft', tracking=True, string='Estado')
    line_ids = fields.One2many(
        'acta.clasificacion.line',
        'acta_id',
        string='Líneas de Clasificación',
    )
    picking_ids = fields.Many2many(
        'stock.picking',
        'acta_clasificacion_picking_rel',
        'acta_id',
        'picking_id',
        string='Transferencias',
        copy=False,
    )
    picking_count = fields.Integer(
        string='Transferencias',
        compute='_compute_picking_count',
    )

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for acta in self:
            acta.picking_count = len(acta.picking_ids)

    def action_validate(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('El acta ya fue validada.'))
        if not self.line_ids:
            raise UserError(_('Agregue al menos una línea de clasificación.'))
        # Asignar folio ANTES de generar movimientos para que el origen sea correcto
        seq = self.env['ir.sequence'].next_by_code('acta.clasificacion')
        if seq:
            self.name = seq
        self._generate_moves()
        self.state = 'done'
        return True

    def _get_or_create_variant(self, template, attr_value):
        """Find or create product variant for the given Condición attribute value."""
        condicion_attr = self.env.ref('lieb_puros_heridos.product_attribute_condicion')

        attr_line = template.attribute_line_ids.filtered(
            lambda l: l.attribute_id == condicion_attr
        )
        if not attr_line:
            raise UserError(_(
                'El producto "%s" no tiene el atributo Condición configurado.'
            ) % template.name)

        if attr_value not in attr_line.value_ids:
            attr_line.write({'value_ids': [(4, attr_value.id)]})
            self.env.flush_all()

        ptav = self.env['product.template.attribute.value'].with_context(
            active_test=False
        ).search([
            ('product_tmpl_id', '=', template.id),
            ('product_attribute_value_id', '=', attr_value.id),
        ], limit=1)
        if not ptav:
            raise UserError(_(
                'No se encontró el valor de atributo "%s" en "%s".'
            ) % (attr_value.name, template.name))

        # Buscar primero si ya existe la variante (activa o archivada)
        variant = self.env['product.product'].with_context(active_test=False).search([
            ('product_tmpl_id', '=', template.id),
            ('product_template_attribute_value_ids', 'in', [ptav.id]),
        ], limit=1)

        if variant:
            if not variant.active:
                variant.active = True
            return variant

        # No existe — activar PTAV y forzar creación
        if not ptav.ptav_active:
            ptav.sudo().write({'ptav_active': True})
        self.env.flush_all()
        self.env.invalidate_all()
        template.sudo()._create_variant_ids()
        self.env.flush_all()
        self.env.invalidate_all()

        variant = self.env['product.product'].with_context(active_test=False).search([
            ('product_tmpl_id', '=', template.id),
            ('product_template_attribute_value_ids', 'in', [ptav.id]),
        ], limit=1)

        if not variant:
            # _create_variant_ids no la creó — creación directa
            variant = self.env['product.product'].sudo().create({
                'product_tmpl_id': template.id,
                'product_template_attribute_value_ids': [(4, ptav.id)],
            })
            self.env.flush_all()

        if not variant.active:
            variant.sudo().write({'active': True})

        return variant

    def _generate_moves(self):
        val_linea = self.env.ref('lieb_puros_heridos.product_attribute_value_linea')
        val_h20 = self.env.ref('lieb_puros_heridos.product_attribute_value_herido_20')
        val_h40 = self.env.ref('lieb_puros_heridos.product_attribute_value_herido_40')
        val_tol = self.env.ref('lieb_puros_heridos.product_attribute_value_tolerable')
        loc_adj = self.env['stock.location'].search(
            [('usage', '=', 'inventory'), ('active', '=', True)], limit=1
        )
        if not loc_adj:
            raise UserError(_('No se encontró una ubicación virtual de tipo "Inventario" en el sistema.'))
        loc_picado = self.env.ref('lieb_puros_heridos.location_virtual_picado')

        pickings = self.env['stock.picking']
        int_type = self.env['stock.picking.type'].search(
            [('code', '=', 'internal')], limit=1
        )

        for line in self.line_ids:
            template = line.product_id
            variant_linea = self._get_or_create_variant(template, val_linea)

            reclasif = [
                (val_h20, line.qty_herido_20),
                (val_h40, line.qty_herido_40),
                (val_tol, line.qty_tolerable),
            ]
            for attr_val, qty in reclasif:
                if qty <= 0:
                    continue
                variant_dest = self._get_or_create_variant(template, attr_val)
                pick_out = self._make_picking(
                    int_type, variant_linea, qty,
                    self.ubicacion_id, loc_adj,
                    '%s – %s: salida Línea' % (self.name, template.name),
                )
                pick_in = self._make_picking(
                    int_type, variant_dest, qty,
                    loc_adj, self.ubicacion_id,
                    '%s – %s: entrada %s' % (self.name, template.name, attr_val.name),
                )
                pickings |= pick_out | pick_in

            if line.qty_picado > 0:
                scrap = self.env['stock.scrap'].create({
                    'product_id': variant_linea.id,
                    'product_uom_id': variant_linea.uom_id.id,
                    'scrap_qty': line.qty_picado,
                    'location_id': self.ubicacion_id.id,
                    'scrap_location_id': loc_picado.id,
                    'origin': self.name,
                })
                scrap.action_validate()

        self.picking_ids = [(4, p.id) for p in pickings]

    def _make_picking(self, picking_type, product, qty, loc_from, loc_to, name):
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': loc_from.id,
            'location_dest_id': loc_to.id,
            'origin': self.name,
            'move_ids': [(0, 0, {
                'name': name,
                'product_id': product.id,
                'product_uom': product.uom_id.id,
                'product_uom_qty': qty,
                'location_id': loc_from.id,
                'location_dest_id': loc_to.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()

        if picking.move_line_ids:
            picking.move_line_ids.write({'quantity': qty})
        else:
            self.env['stock.move.line'].create({
                'picking_id': picking.id,
                'move_id': picking.move_ids[0].id,
                'product_id': product.id,
                'product_uom_id': product.uom_id.id,
                'quantity': qty,
                'location_id': loc_from.id,
                'location_dest_id': loc_to.id,
            })

        picking.with_context(skip_backorder=True, skip_immediate=True).button_validate()
        return picking

    def action_view_pickings(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Transferencias'),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.picking_ids.ids)],
        }


class ActaClasificacionLine(models.Model):
    _name = 'acta.clasificacion.line'
    _description = 'Línea de Acta de Clasificación'

    acta_id = fields.Many2one(
        'acta.clasificacion',
        required=True,
        ondelete='cascade',
    )
    momento = fields.Selection(
        related='acta_id.momento', store=True, readonly=True,
        string='Momento',
    )
    fecha = fields.Date(
        related='acta_id.fecha', store=True, readonly=True,
        string='Fecha',
    )
    product_id = fields.Many2one(
        'product.template',
        string='Producto',
        required=True,
    )
    qty_herido_20 = fields.Float(string='Herido 20%', default=0.0, digits=(12, 2))
    qty_herido_40 = fields.Float(string='Herido 40%', default=0.0, digits=(12, 2))
    qty_tolerable = fields.Float(string='Tolerable', default=0.0, digits=(12, 2))
    qty_picado = fields.Float(string='Picado', default=0.0, digits=(12, 2))
    total_clasificado = fields.Float(
        string='Total',
        compute='_compute_total',
        store=True,
        digits=(12, 2),
    )

    @api.depends('qty_herido_20', 'qty_herido_40', 'qty_tolerable', 'qty_picado')
    def _compute_total(self):
        for line in self:
            line.total_clasificado = (
                line.qty_herido_20 + line.qty_herido_40
                + line.qty_tolerable + line.qty_picado
            )

    @api.constrains('qty_herido_20', 'qty_herido_40', 'qty_tolerable', 'qty_picado')
    def _check_quantities(self):
        for line in self:
            if any(
                q < 0
                for q in [line.qty_herido_20, line.qty_herido_40, line.qty_tolerable, line.qty_picado]
            ):
                raise ValidationError(_('Las cantidades no pueden ser negativas.'))
            total = (
                line.qty_herido_20 + line.qty_herido_40
                + line.qty_tolerable + line.qty_picado
            )
            if total == 0:
                raise ValidationError(_(
                    'Al menos una cantidad debe ser mayor a cero en el producto "%s".'
                ) % line.product_id.name)
