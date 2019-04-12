# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from odoo.addons.component.core import Component

from odoo import models, fields, api, exceptions, _

from ...components.backend_adapter import api_handle_errors
from odoo.addons.connector.checkpoint import checkpoint
from odoo.addons.base.res.res_partner import _tz_get

_logger = logging.getLogger(__name__)


class PrestashopBackend(models.Model):
    _inherit = 'prestashop.backend'

    export_products_since = fields.Datetime('Export Products since')

    @api.multi
    def export_products(self):
        for backend_record in self:
            since_date = backend_record.export_products_since
            self.env['prestashop.product.template'].with_delay(
            ).export_products(backend_record, since_date)
        return True

    @api.model
    def _scheduler_export_products(self, domain=None):
        self.search(domain or []).export_products()
