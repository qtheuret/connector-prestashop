# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo.addons.component.core import Component


class ProductProductImporter(Component):
    _name = 'prestashop.product.product.sync.importer'
    _inherit = 'prestashop.auto.matching.importer'
    _apply_on = 'prestashop.product.combination'

    _erp_field = 'default_code'
    _ps_field = 'reference'

    def _compare_function(self, ps_val, erp_val, ps_dict, erp_dict):
        return ps_val == erp_val