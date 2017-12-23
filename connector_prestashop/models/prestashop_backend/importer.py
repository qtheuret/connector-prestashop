# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo import _
from odoo.addons.connector.unit.mapper import ImportMapper, mapping
from ...components.importer import PrestashopImporter, DirectBatchImporter
from ...backend import prestashop
from odoo.addons.component.core import Component

@prestashop
class ShopGroupImportMapper(ImportMapper):
    _model_name = 'prestashop.shop.group'

    direct = [('name', 'name')]

    @mapping
    def name(self, record):
        name = record['name']
        if name is None:
            name = _('Undefined')
        return {'name': name}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}


class MetadataBatchImporter(Component):
    """ Import the records directly, without delaying the jobs.

    Import the PrestShop Websites, Stores, Storeviews

    They are imported directly because this is a rare and fast operation,
    and we don't really bother if it blocks the UI during this time.
    (that's also a mean to rapidly check the connectivity with Magento).

    """

    _name = 'prestashop.metadata.batch.importer'
    _inherit = 'prestashop.direct.batch.importer'
    _apply_on = [
        'prestashop.shop.group',
    ]


@prestashop
class ShopGroupImporter(PrestashopImporter):
    _model_name = 'prestashop.shop.group'


@prestashop
class ShopGroupBatchImporter(DirectBatchImporter):
    _model_name = 'prestashop.shop.group'
