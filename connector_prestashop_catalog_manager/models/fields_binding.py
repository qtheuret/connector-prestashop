from odoo import models, fields, api


class FieldBinding(models.Model):
    _name = 'prestashop.field.binding'

    backend_id = fields.Many2one(
        comodel_name='prestashop.backend',
        string='Backend',
        required=True,
    )
    odoo_model = fields.Char(
        string='Odoo model',
        required=True,
    )
    prestashop_model = fields.Char(
        string='Prestashop model',
        required=True,
    )
    prestashop_field = fields.Char(
        string='Prestashop field name',
        required=True
    )
    odoo_field = fields.Many2one(
        comodel_name='ir.model.fields',
    )
    direction = fields.Selection(
        selection=[
            ('from_prestashop', 'PS -> Odoo'),
            ('to_prestashop', 'Odoo -> PS'),
        ],
        string='Direction',
        required=True,
        default='to_prestashop',
    )
    active = fields.Boolean(
        string='Active',
        default=lambda *a: True,
    )
