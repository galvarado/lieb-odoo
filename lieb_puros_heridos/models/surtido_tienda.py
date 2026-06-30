from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class SurtidoTienda(models.Model):
    _name = 'surtido.tienda'
    _description = 'Surtido de Inventario a Tienda'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, name desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Referencia',
        readonly=True,
        copy=False,
        default=lambda self: _('Nuevo'),
    )
    date = fields.Date(
        string='Fecha',
        default=fields.Date.today,
        required=True,
        tracking=True,
    )
    warehouse_src_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén Origen',
        required=True,
        tracking=True,
    )
    warehouse_dest_id = fields.Many2one(
        'stock.warehouse',
        string='Tienda Destino',
        required=True,
        tracking=True,
    )
    chofer = fields.Char(string='Chofer')
    firma_chofer = fields.Binary(string='Firma Chofer')
    requisicion_id = fields.Many2one(
        'requisicion.surtido',
        string='Requisición',
        copy=False,
        tracking=True,
    )
    observaciones = fields.Text(string='Observaciones')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('sent', 'En Tránsito'),
        ('received', 'Recibido'),
        ('cancelled', 'Cancelado'),
    ], default='draft', tracking=True, string='Estado')

    line_ids = fields.One2many(
        'surtido.tienda.line',
        'surtido_id',
        string='Líneas',
    )
    picking_out_ids = fields.Many2many(
        'stock.picking',
        'surtido_tienda_picking_out_rel',
        'surtido_id', 'picking_id',
        string='Salidas (ALM→Tránsito)',
        copy=False,
    )
    picking_in_ids = fields.Many2many(
        'stock.picking',
        'surtido_tienda_picking_in_rel',
        'surtido_id', 'picking_id',
        string='Entradas (Tránsito→Tienda)',
        copy=False,
    )
    picking_return_ids = fields.Many2many(
        'stock.picking',
        'surtido_tienda_picking_return_rel',
        'surtido_id', 'picking_id',
        string='Rechazos',
        copy=False,
    )
    picking_out_count = fields.Integer(compute='_compute_picking_counts')
    picking_in_count = fields.Integer(compute='_compute_picking_counts')
    picking_return_count = fields.Integer(compute='_compute_picking_counts')
    return_pending_count = fields.Integer(
        string='Rechazos Pendientes',
        compute='_compute_picking_counts',
    )
    transit_count = fields.Integer(
        string='Pendientes de Recepción',
        compute='_compute_picking_counts',
    )

    @api.depends(
        'picking_out_ids', 'picking_in_ids', 'picking_in_ids.state',
        'picking_return_ids', 'picking_return_ids.state',
    )
    def _compute_picking_counts(self):
        for rec in self:
            rec.picking_out_count = len(rec.picking_out_ids)
            rec.picking_in_count = len(rec.picking_in_ids)
            rec.picking_return_count = len(rec.picking_return_ids)
            rec.return_pending_count = len(
                rec.picking_return_ids.filtered(lambda p: p.state not in ('done', 'cancel'))
            )
            rec.transit_count = len(
                rec.picking_in_ids.filtered(lambda p: p.state not in ('done', 'cancel'))
            )

    # ── Constraints ───────────────────────────────────────────────────────────

    @api.constrains('warehouse_src_id', 'warehouse_dest_id')
    def _check_warehouses(self):
        for rec in self:
            if rec.warehouse_src_id == rec.warehouse_dest_id:
                raise ValidationError(_('El almacén origen y destino no pueden ser el mismo.'))

    # ── Helpers de ubicación ──────────────────────────────────────────────────

    def _ensure_heridos_loc(self, warehouse):
        loc = self.env['stock.location'].search([
            ('name', '=', 'Heridos'),
            ('location_id', '=', warehouse.lot_stock_id.id),
            ('usage', '=', 'internal'),
            ('active', 'in', [True, False]),
        ], limit=1)
        if not loc:
            loc = self.env['stock.location'].create({
                'name': 'Heridos',
                'location_id': warehouse.lot_stock_id.id,
                'usage': 'internal',
            })
        elif not loc.active:
            loc.active = True
        return loc

    def _route_line(self, line):
        """Return (location_src, location_dest) for a surtido line."""
        condicion = line.product_id.lieb_condicion or ''
        loc_alm_stock = self.warehouse_src_id.lot_stock_id
        loc_alm_heridos = self.env.ref('lieb_puros_heridos.location_alm_heridos')
        loc_tienda_stock = self.warehouse_dest_id.lot_stock_id
        loc_tienda_heridos = self._ensure_heridos_loc(self.warehouse_dest_id)

        if condicion == 'Línea':
            return loc_alm_stock, loc_tienda_stock
        elif condicion in ('Herido 20%', 'Herido 40%'):
            return loc_alm_heridos, loc_tienda_heridos
        elif condicion == 'Tolerable':
            return loc_alm_heridos, loc_tienda_stock
        else:
            # Sin condición definida → existencias estándar
            return loc_alm_stock, loc_tienda_stock

    # ── Acciones ──────────────────────────────────────────────────────────────

    def action_send(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('El surtido ya fue enviado.'))
        if not self.line_ids:
            raise UserError(_('Agregue al menos una línea antes de enviar.'))
        if not self.chofer:
            raise UserError(_('Registre el nombre del chofer antes de enviar.'))

        seq = self.env['ir.sequence'].next_by_code('surtido.tienda')
        if seq:
            self.name = seq

        loc_transit = self.env.ref('lieb_puros_heridos.location_transit_surtido')
        int_type_src = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', self.warehouse_src_id.id),
        ], limit=1) or self.env['stock.picking.type'].search(
            [('code', '=', 'internal')], limit=1
        )
        int_type_dest = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', self.warehouse_dest_id.id),
        ], limit=1) or int_type_src

        # Agrupar líneas por (src, dest)
        groups = {}
        for line in self.line_ids:
            loc_src, loc_dest = self._route_line(line)
            key = (loc_src.id, loc_dest.id)
            groups.setdefault(key, []).append((line, loc_src, loc_dest))

        pickings_out = self.env['stock.picking']
        pickings_in = self.env['stock.picking']

        for (loc_src_id, loc_dest_id), lines in groups.items():
            loc_src = lines[0][1]
            loc_dest = lines[0][2]

            # OUT: ALM/origen → Tránsito  (validado inmediatamente)
            picking_out = self._create_picking(
                int_type_src, loc_src, loc_transit,
                [(l.product_id, l.qty) for l, _, _ in lines],
                immediate=True,
            )
            pickings_out |= picking_out

            # IN: Tránsito → TIENDA/destino  (queda asignado para tienda)
            picking_in = self._create_picking(
                int_type_dest, loc_transit, loc_dest,
                [(l.product_id, l.qty) for l, _, _ in lines],
                immediate=False,
            )
            pickings_in |= picking_in

        self.picking_out_ids = [(4, p.id) for p in pickings_out]
        self.picking_in_ids = [(4, p.id) for p in pickings_in]
        self.state = 'sent'

        if self.requisicion_id and self.requisicion_id.state == 'sent':
            self.requisicion_id.state = 'fulfilled'

        self.message_post(body=_('Surtido enviado. Chofer: %s.') % self.chofer)

    def _create_picking(self, picking_type, loc_from, loc_to, product_qtys, immediate=False):
        company = picking_type.company_id or self.env.company

        # Crear picking primero (sin moves) para que company_id quede en DB
        # antes de que los moves hereden vía related picking_id.company_id
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': loc_from.id,
            'location_dest_id': loc_to.id,
            'origin': self.name,
            'company_id': company.id,
        })
        self.env['stock.move'].create([{
            'name': self.name,
            'picking_id': picking.id,
            'product_id': product.id,
            'product_uom': product.uom_id.id,
            'product_uom_qty': qty,
            'location_id': loc_from.id,
            'location_dest_id': loc_to.id,
        } for product, qty in product_qtys])
        picking.action_confirm()
        picking.action_assign()

        if immediate:
            if picking.move_line_ids:
                for ml in picking.move_line_ids:
                    ml.quantity = ml.move_id.product_uom_qty
            else:
                for move in picking.move_ids:
                    self.env['stock.move.line'].create({
                        'picking_id': picking.id,
                        'move_id': move.id,
                        'product_id': move.product_id.id,
                        'product_uom_id': move.product_uom.id,
                        'quantity': move.product_uom_qty,
                        'location_id': move.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'company_id': picking.company_id.id,
                    })
            picking.with_context(skip_backorder=True, skip_immediate=True).button_validate()

        return picking

    def action_cancel(self):
        self.ensure_one()
        if self.state == 'draft':
            self.state = 'cancelled'
            return
        if self.state not in ('sent', 'received'):
            raise UserError(_('No se puede cancelar en este estado.'))

        # Devolver pickings IN pendientes a tránsito
        for picking in self.picking_in_ids.filtered(lambda p: p.state not in ('done', 'cancel')):
            picking.action_cancel()

        # Revertir pickings OUT ya validados (tránsito → origen)
        for picking in self.picking_out_ids.filtered(lambda p: p.state == 'done'):
            try:
                wizard = self.env['stock.return.picking'].with_context(
                    active_id=picking.id, active_ids=picking.ids,
                ).create({'picking_id': picking.id})
                wizard._onchange_picking_id()
                action = wizard.create_returns()
                return_pick = self.env['stock.picking'].browse(action['res_id'])
                return_pick.with_context(
                    skip_backorder=True, skip_immediate=True
                ).button_validate()
            except Exception:
                pass

        self.state = 'cancelled'
        self.message_post(body=_('Surtido cancelado.'))

    def action_receive_with_review(self):
        self.ensure_one()
        if self.state != 'sent':
            raise UserError(_('Solo se puede recibir un surtido en tránsito.'))
        wizard = self.env['wizard.recepcion.surtido'].create_for_surtido(self)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Recepción Parcial'),
            'res_model': 'wizard.recepcion.surtido',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_receive_all(self):
        self.ensure_one()
        if self.state != 'sent':
            raise UserError(_('Solo se puede recibir un surtido en tránsito.'))
        pending = self.picking_in_ids.filtered(lambda p: p.state not in ('done', 'cancel'))
        if not pending:
            raise UserError(_('No hay pickings pendientes de recepción.'))
        for picking in pending:
            if picking.move_line_ids:
                for ml in picking.move_line_ids:
                    ml.quantity = ml.move_id.product_uom_qty
            else:
                for move in picking.move_ids:
                    self.env['stock.move.line'].create({
                        'picking_id': picking.id,
                        'move_id': move.id,
                        'product_id': move.product_id.id,
                        'product_uom_id': move.product_uom.id,
                        'quantity': move.product_uom_qty,
                        'location_id': move.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'company_id': picking.company_id.id,
                    })
            picking.with_context(skip_backorder=True, skip_immediate=True).button_validate()
        self.action_check_received()
        self.message_post(body=_('Recepción completa registrada.'))

    def action_check_received(self):
        for rec in self.filtered(lambda s: s.state == 'sent'):
            if all(p.state == 'done' for p in rec.picking_in_ids):
                rec.state = 'received'

    def action_view_pickings_out(self):
        return self._action_view_pickings(self.picking_out_ids, _('Salidas'))

    def action_view_pickings_in(self):
        return self._action_view_pickings(self.picking_in_ids, _('Entradas'))

    def action_view_pickings_return(self):
        return self._action_view_pickings(self.picking_return_ids, _('Rechazos'))

    def _action_view_pickings(self, pickings, title):
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', pickings.ids)],
        }

    def _get_report_lines(self):
        """Consolidate sent/received/rejected data per product for the receipt report."""
        loc_transit = self.env.ref('lieb_puros_heridos.location_transit_surtido')

        # Moves received: done IN pickings
        received_by_product = {}
        for picking in self.picking_in_ids.filtered(lambda p: p.state == 'done'):
            for ml in picking.move_line_ids:
                pid = ml.product_id.id
                received_by_product[pid] = received_by_product.get(pid, 0.0) + ml.quantity

        # Moves rejected: return pickings from transit (origin = surtido name)
        return_pickings = self.env['stock.picking'].search([
            ('origin', '=', self.name),
            ('location_id', '=', loc_transit.id),
            ('state', 'not in', ['cancel']),
        ])
        rejected_by_product = {}
        motivo_by_product = {}
        for picking in return_pickings:
            for move in picking.move_ids:
                pid = move.product_id.id
                rejected_by_product[pid] = rejected_by_product.get(pid, 0.0) + move.product_uom_qty
                if move.motivo_retorno_id and pid not in motivo_by_product:
                    motivo_by_product[pid] = move.motivo_retorno_id.name

        lines = []
        for line in self.line_ids:
            pid = line.product_id.id
            recibida = received_by_product.get(pid, 0.0)
            rechazada = rejected_by_product.get(pid, 0.0)
            lines.append({
                'product': line.product_id.display_name,
                'condicion': line.condicion or '',
                'enviada': line.qty,
                'recibida': recibida,
                'rechazada': rechazada,
                'motivo': motivo_by_product.get(pid, ''),
            })
        return lines


class SurtidoTiendaLine(models.Model):
    _name = 'surtido.tienda.line'
    _description = 'Línea de Surtido a Tienda'

    surtido_id = fields.Many2one(
        'surtido.tienda',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto (Variante)',
        required=True,
        domain=[('active', '=', True)],
    )
    qty = fields.Float(string='Cantidad', required=True, digits=(12, 2))
    condicion = fields.Char(
        string='Condición',
        related='product_id.lieb_condicion',
        readonly=True,
        store=True,
    )
    location_src_id = fields.Many2one(
        'stock.location',
        string='Ubicación Origen',
        compute='_compute_locations',
        store=True,
        readonly=True,
    )
    location_dest_id = fields.Many2one(
        'stock.location',
        string='Ubicación Destino',
        compute='_compute_locations',
        store=True,
        readonly=True,
    )

    @api.depends(
        'product_id', 'product_id.lieb_condicion',
        'surtido_id.warehouse_src_id', 'surtido_id.warehouse_dest_id',
    )
    def _compute_locations(self):
        for line in self:
            if line.product_id and line.surtido_id.warehouse_src_id and line.surtido_id.warehouse_dest_id:
                src, dest = line.surtido_id._route_line(line)
                line.location_src_id = src
                line.location_dest_id = dest
            else:
                line.location_src_id = False
                line.location_dest_id = False

    @api.constrains('qty')
    def _check_qty(self):
        for line in self:
            if line.qty <= 0:
                raise ValidationError(_('La cantidad debe ser mayor a cero.'))
