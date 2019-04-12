# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import datetime
import logging

from slugify import slugify

from odoo import fields, _

from odoo.addons.component.core import Component
from odoo.addons.connector.components.mapper import mapping , external_to_m2o


_logger = logging.getLogger(__name__)
try:
    from prestapyt import PrestaShopWebServiceError
except:
    _logger.debug('Cannot import from `prestapyt`')


class ProductCategoryExporter(Component):
    _name = 'prestashop.product.category.exporter'
    _inherit = 'translation.prestashop.exporter'
    _apply_on = 'prestashop.product.category'
    _model_name = 'prestashop.product.category'

    _translatable_fields = {
        'prestashop.product.category': [
            'name',
            'description',
            'link_rewrite',
            'meta_description',
            'meta_keywords',
            'meta_title',
        ]
    }

    def _export_dependencies(self):
        """ Export the parent product category."""
        record = self.binding and self.binding.odoo_id
        if record and record.parent_id:
            self._export_dependency(record.parent_id, 'prestashop.product.category')
