# -*- coding: utf-8 -*-
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import models, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.multi
    def update_prestashop_qty(self):
        """
        If the product is in a BoM line,
        update the PrestaShop quantity of the main
        product of the BoM.
        """
        bom_line_obj = self.env['mrp.bom.line']

        res = super(ProductProduct, self).update_prestashop_qty()

        for product in self:
            bom_lines = bom_line_obj.search([
                ('product_id', '=', product.id),
            ])
            for l in bom_lines:
                if l.bom_id.product_id:
                    l.bom_id.product_id.update_prestashop_qty()
                if l.bom_id.product_tmpl_id:
                    for prestashop_product in \
                        l.bom_id.product_tmpl_id.prestashop_bind_ids:
                        prestashop_product.recompute_prestashop_qty()

        return res

