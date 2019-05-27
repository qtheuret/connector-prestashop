# -*- coding: utf-8 -*-
# © 2016 Sergio Teruel <sergio.teruel@tecnativa.com>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from openerp import models, fields, api
import openerp.addons.decimal_precision as dp
from odoo.addons.component.core import Component

from odoo.addons.queue_job.job import job, related_action


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def create(self, vals):
        res = super(ProductTemplate, self).create(vals)

        if not self.env.context.get('create_bindings'):
            for backend in self.env['prestashop.backend'].search([]):
                res.create_prestashop_bindings(backend.id)

        return res

    @api.multi
    def write(self, vals):
        res = super(ProductTemplate, self).write(vals)

        if not self.env.context.get('create_bindings'):
            for backend in self.env['prestashop.backend'].search([]):
                self.create_prestashop_bindings(backend.id)

        return res


    def create_prestashop_bindings(self, backend_id):
        shop_id = False
        for record in self:
            if not record.prestashop_bind_ids.filtered(lambda s: s.backend_id.id == backend_id):
                if not shop_id:
                    shops = self.env['prestashop.shop'].search([('backend_id', '=', backend_id)])
                    if shops:
                        shop_id = shops[0].id
                self.env['prestashop.product.template'].with_context({'create_bindings': True}).create({
                    'backend_id': backend_id,
                    'odoo_id': record.id,
                    'default_shop_id': shop_id,
                })


class TemplateAdapter(Component):
    _name = 'prestashop.product.template.adapter'
    _inherit = 'prestashop.adapter'
    _apply_on = 'prestashop.product.template'
    _prestashop_model = 'products'
    _export_node_name = 'product'
    _export_node_name_res = 'product'


class PrestashopProductTemplate(models.Model):
    _inherit = 'prestashop.product.template'

    meta_title = fields.Char(
        string='Meta Title',
        translate=True
    )
    meta_description = fields.Char(
        string='Meta Description',
        translate=True
    )
    meta_keywords = fields.Char(
        string='Meta Keywords',
        translate=True
    )
    tags = fields.Char(
        string='Tags',
        translate=True
    )
    online_only = fields.Boolean(string='Online Only')
    additional_shipping_cost = fields.Float(
        string='Additional Shipping Price',
        digits_compute=dp.get_precision('Product Price'),
        help="Additionnal Shipping Price for the product on Prestashop")
    available_now = fields.Char(
        string='Available Now',
        translate=True
    )
    available_later = fields.Char(
        string='Available Later',
        translate=True
    )
    available_date = fields.Date(string='Available Date')
    minimal_quantity = fields.Integer(
        string='Minimal Quantity',
        help='Minimal Sale quantity',
        default=1,
    )
    delivery_in_stock = fields.Char(
        string='Delivery time of in-stock products',
        size=255,
        translate=True,
    )
    delivery_out_stock = fields.Char(
        string='Delivery time of out-of-stock products with allowed orders',
        size=255,
        translate=True,
    )
    id_group_shop = fields.Many2one(
        comodel_name='prestashop.shop.group',
        string='Shops group',
    )
