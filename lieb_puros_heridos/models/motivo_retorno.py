from odoo import fields, models


class MotivoRetorno(models.Model):
    _name = 'motivo.retorno'
    _description = 'Motivo de Retorno / Rechazo'
    _order = 'sequence, name'

    name = fields.Char(string='Motivo', required=True)
    tipo = fields.Selection([
        ('dano', 'Daño'),
        ('discrepancia', 'Discrepancia'),
    ], string='Tipo', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
