from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class RequisicionSurtido(models.Model):
    _name = 'requisicion.surtido'
    _description = 'Requisición de Surtido de Tienda'
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
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Tienda Solicitante',
        required=True,
        tracking=True,
    )
    warehouse_src_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén Origen',
        required=True,
        tracking=True,
    )
    responsable_id = fields.Many2one(
        'res.users',
        string='Responsable',
        default=lambda self: self.env.user,
    )
    observaciones = fields.Text(string='Observaciones')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('sent', 'Enviada'),
        ('fulfilled', 'Surtida'),
        ('cancelled', 'Cancelada'),
    ], default='draft', tracking=True, string='Estado')

    line_ids = fields.One2many(
        'requisicion.surtido.line',
        'requisicion_id',
        string='Productos Solicitados',
    )
    surtido_ids = fields.Many2many(
        'surtido.tienda',
        'surtido_tienda_requisicion_rel',
        'requisicion_id', 'surtido_id',
        string='Surtidos Generados',
        copy=False,
    )
    surtido_count = fields.Integer(compute='_compute_surtido_count')

    @api.depends('surtido_ids')
    def _compute_surtido_count(self):
        for rec in self:
            rec.surtido_count = len(rec.surtido_ids)

    def action_send(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('La requisición ya fue enviada.'))
        if not self.line_ids:
            raise UserError(_('Agregue al menos un producto.'))
        seq = self.env['ir.sequence'].next_by_code('requisicion.surtido')
        if seq:
            self.name = seq
        self.state = 'sent'

    def action_cancel(self):
        self.ensure_one()
        if self.state in ('fulfilled',):
            raise UserError(_('No se puede cancelar una requisición ya surtida.'))
        self.state = 'cancelled'

    def action_create_surtido(self):
        self.ensure_one()
        if self.state not in ('sent',):
            raise UserError(_('Solo se puede crear un surtido desde una requisición enviada.'))

        surtido = self.env['surtido.tienda'].create({
            'requisicion_id': self.id,
            'warehouse_src_id': self.warehouse_src_id.id,
            'warehouse_dest_id': self.warehouse_id.id,
            'line_ids': [(0, 0, {
                'product_id': line.product_id.id,
                'qty': line.qty_requested,
            }) for line in self.line_ids],
        })
        self.surtido_ids = [(4, surtido.id)]

        return {
            'type': 'ir.actions.act_window',
            'name': _('Surtido a Tienda'),
            'res_model': 'surtido.tienda',
            'res_id': surtido.id,
            'view_mode': 'form',
        }

    def action_view_surtidos(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Surtidos'),
            'res_model': 'surtido.tienda',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.surtido_ids.ids)],
        }


class RequisicionSurtidoLine(models.Model):
    _name = 'requisicion.surtido.line'
    _description = 'Línea de Requisición de Surtido'

    requisicion_id = fields.Many2one(
        'requisicion.surtido',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto (Variante)',
        required=True,
    )
    qty_requested = fields.Float(
        string='Cantidad Solicitada',
        required=True,
        digits=(12, 2),
    )
    condicion = fields.Char(
        string='Condición',
        related='product_id.lieb_condicion',
        readonly=True,
    )

    @api.constrains('qty_requested')
    def _check_qty(self):
        for line in self:
            if line.qty_requested <= 0:
                raise ValidationError(_('La cantidad debe ser mayor a cero.'))
