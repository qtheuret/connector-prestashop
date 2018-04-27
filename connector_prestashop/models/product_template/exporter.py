# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo.addons.component.core import Component


class ProductInventoryExporter(Component):
    _name = 'prestashop.product.template.inventory.exporter'
    _inherit = 'prestashop.exporter'
    _apply_on = 'prestashop.product.template'
    _usage = 'inventory.exporter'

    def get_filter(self, template):
        binder = self.binder_for()
        prestashop_id = binder.to_external(template.id)
        return {
            'filter[id_product]': prestashop_id,
            'filter[id_product_attribute]': 0
        }

    def run(self, template, fields):
        """ Export the product inventory to PrestaShop """
        adapter = self.component(
            usage='backend.adapter', model_name='_import_stock_available'
        )
        filter = self.get_filter(template)
        adapter.export_quantity(filter, int(template.quantity))
