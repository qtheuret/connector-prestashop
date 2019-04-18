# -*- coding: utf-8 -*-
# © 2016 Sergio Teruel <sergio.teruel@tecnativa.com>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from openerp import models, fields
import openerp.addons.decimal_precision as dp
from odoo.addons.component.core import Component


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    prestashop_delivery_in_stock = fields.Char(
        string='Delivery time of in-stock products',
        size=255,
    )
    prestashop_delivery_out_stock = fields.Char(
        string='Delivery time of out-of-stock products with allowed orders',
        size=255
    )

    def create_prestashop_bindings(self, backend_id):
        shop_id = False
        for record in self:
            if not record.prestashop_bind_ids.filtered(lambda s: s.backend_id.id == backend_id):
                if not shop_id:
                    shops = self.env['prestashop.shop'].search([('backend_id', '=', backend_id)])
                    if shops:
                        shop_id = shops[0].id
                self.env['prestashop.product.template'].create({
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
