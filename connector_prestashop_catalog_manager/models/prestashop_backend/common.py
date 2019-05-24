# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
import datetime

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class PrestashopBackend(models.Model):
    _inherit = 'prestashop.backend'

    export_products_since = fields.Datetime('Export Products since')

    @api.multi
    def export_products(self):
        for backend_record in self:
            since_date = backend_record.export_products_since
            new_product_sync_date = datetime.datetime.now()

            filters = [
                ('no_export', '=', False),
                ('write_date', '<=', fields.Datetime.to_string(new_product_sync_date))
            ]
            if since_date:
                filters.append(('write_date', '>=', since_date))

            # Products
            products = self.env['product.product'].search(filters)
            for prd in products:
                if not prd.attribute_value_ids:
                    # Do not sync product.product for no variant product, only sync. product.template
                    prd.product_tmpl_id.create_prestashop_bindings(backend_record.id)
                    for bind in prd.product_tmpl_id.prestashop_bind_ids.filtered(lambda s: s.backend_id.id == backend_record.id and not s.no_export):
                        bind.with_delay().export_record()
                else:
                    # Create bindings if not exists
                    prd.create_prestashop_bindings(backend_record.id)
                    for bind in prd.prestashop_bind_ids.filtered(lambda s: s.backend_id.id == backend_record.id and not s.no_export):
                        bind.with_delay().export_record()

            backend_record.export_products_since = fields.Datetime.to_string(new_product_sync_date)

        return True

    @api.model
    def _scheduler_export_products(self, domain=None):
        self.search(domain or []).export_products()
