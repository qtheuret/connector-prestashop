# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo.addons.component.core import Component


class CombinationInventoryExporter(Component):
    _name = 'prestashop.product.combination.inventory.exporter'
    _inherit = 'prestashop.product.template.inventory.exporter'
    _apply_on = 'prestashop.product.combination'

    def get_filter(self, template):
        return {
            'filter[id_product]': template.main_template_id.prestashop_id,
            'filter[id_product_attribute]': template.prestashop_id,
        }
