# -*- coding: utf-8 -*-
###############################################################################
#                                                                             #
#   Prestashoperpconnect for OpenERP                                          #
#   Copyright (C) 2012 Akretion                                               #
#   Author :                                                                  #
#           Sébastien BEAU <sebastien.beau@akretion.com>                      #
#           Benoît GUILLOT <benoit.guillot@akretion.com>                      #
#                                                                             #
#   This program is free software: you can redistribute it and/or modify      #
#   it under the terms of the GNU Affero General Public License as            #
#   published by the Free Software Foundation, either version 3 of the        #
#   License, or (at your option) any later version.                           #
#                                                                             #
#   This program is distributed in the hope that it will be useful,           #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of            #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the             #
#   GNU Affero General Public License for more details.                       #
#                                                                             #
#   You should have received a copy of the GNU Affero General Public License  #
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.     #
#                                                                             #
###############################################################################

import logging
from openerp.osv import fields, orm
from prestapyt import PrestaShopWebServiceError
from ..unit.backend_adapter import (GenericAdapter ,PrestaShopCRUDAdapter)
from ..unit.mapper import PrestashopImportMapper
from openerp.addons.connector.connector import ConnectorUnit
from openerp.addons.connector.exception import FailedJobError
from openerp.addons.connector.exception import NothingToDoJob
from openerp.addons.connector.queue.job import job
from openerp.addons.connector.unit.synchronizer import Importer as ImportSynchronizer
from ..unit.import_synchronizer import PrestashopImportSynchronizer
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from ..backend import prestashop
from ..connector import add_checkpoint
from ..connector import get_environment
from ..unit.exception import OrderImportRuleRetry
from openerp.addons.connector.unit.mapper import (mapping,
                                                  only_create,
                                                  ImportMapper
                                                  )
from ..unit.mapper import (PrestashopImportMapper)
from ..unit.backend_adapter import GenericAdapter
from ..unit.import_synchronizer import DelayedBatchImport
from ..unit.import_synchronizer import import_record

_logger = logging.getLogger(__name__)


class res_partner_category(orm.Model):
    _inherit = 'res.partner.category'

    _columns = {
        'prestashop_bind_ids': fields.one2many(
            'prestashop.res.partner.category',
            'openerp_id',
            string='PrestaShop Bindings',
            readonly=True),
    }


class prestashop_res_partner_category(orm.Model):
    _name = 'prestashop.res.partner.category'
    _inherit = 'prestashop.binding'
    _inherits = {'res.partner.category': 'openerp_id'}

    _columns = {
        'openerp_id': fields.many2one(
            'res.partner.category',
            string='Partner Category',
            required=True,
            ondelete='cascade'
        ),
        'date_add': fields.datetime(
            'Created At (on Prestashop)',
            readonly=True
        ),
        'date_upd': fields.datetime(
            'Updated At (on Prestashop)',
            readonly=True
        ),
        # TODO add prestashop shop when the field will be available in the api.
        # we have reported the bug for it
        # see http://forge.prestashop.com/browse/PSCFV-8284
    }

    _sql_constraints = [
        ('prestashop_uniq', 'unique(backend_id, prestashop_id)',
         'A partner group with the same ID on PrestaShop already exists.'),
    ]


@prestashop
class PartnerCategoryAdapter(GenericAdapter):
    _model_name = 'prestashop.res.partner.category'
    _prestashop_model = 'groups'


@prestashop
class PartnerCategoryImportMapper(PrestashopImportMapper):
    _model_name = 'prestashop.res.partner.category'

    direct = [
        ('name', 'name'),
        ('date_add', 'date_add'),
        ('date_upd', 'date_upd'),
    ]

    @mapping
    def prestashop_id(self, record):
        return {'prestashop_id': record['id']}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def name(self, record):
        _logger.debug("PARTNER CATEGORY MAPPING")
        name = None
        if 'language' in record['name']:
            language_binder = self.get_binder_for_model('prestashop.res.lang')
            languages = record['name']['language']
            if not isinstance(languages, list):
                languages = [languages]
            for lang in languages:
                erp_language_id = language_binder.to_openerp(
                    lang['attrs']['id'])
                if not erp_language_id:
                    continue
                erp_lang = self.session.read(
                    'prestashop.res.lang',
                    erp_language_id.id,
                    []
                )
                if erp_lang['code'] == 'en_US':
                    name = lang['value']
                    break
            if name is None:
                name = languages[0]['value']
        else:
            name = record['name']

        return {'name': name}

@prestashop
class PartnerCategoryRecordImport(PrestashopImportSynchronizer):

    """ Import one translatable record """
    _model_name = [
        'prestashop.res.partner.category',
    ]

    _translatable_fields = {
        'prestashop.res.partner.category': ['name'],
    }

    def _after_import(self, erp_id):
        record = self._get_prestashop_data()
        if float(record['reduction']):
            import_record(
                self.session,
                'prestashop.groups.pricelist',
                self.backend_record.id,
                record['id']
            )

