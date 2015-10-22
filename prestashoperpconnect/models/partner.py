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
from ..unit.backend_adapter import GenericAdapter
from ..unit.backend_adapter import PrestaShopCRUDAdapter
from openerp.addons.connector.connector import ConnectorUnit
from openerp.addons.connector.exception import FailedJobError
from openerp.addons.connector.exception import NothingToDoJob
from openerp.addons.connector.queue.job import job
from openerp.addons.connector.unit.synchronizer import ImportSynchronizer
from ..unit.import_synchronizer import (PrestashopImportSynchronizer
                                        , import_batch)
from openerp.addons.connector.unit.backend_adapter import BackendAdapter
from ..unit.import_synchronizer import import_record
                                        
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from ..backend import prestashop
from ..connector import add_checkpoint
from ..connector import get_environment
from ..unit.exception import OrderImportRuleRetry

_logger = logging.getLogger(__name__)


class res_partner(orm.Model):
    _inherit = 'res.partner'

    _columns = {
        'prestashop_bind_ids': fields.one2many(
            'prestashop.res.partner', 'openerp_id',
            string="PrestaShop Bindings"
        ),
        'prestashop_address_bind_ids': fields.one2many(
            'prestashop.address', 'openerp_id',
            string="PrestaShop Address Bindings"
        ),
        'address_alias': fields.char('Alias in prestashop'),
    }


class prestashop_res_partner(orm.Model):
    _name = 'prestashop.res.partner'
    _inherit = 'prestashop.binding'
    _inherits = {'res.partner': 'openerp_id'}

    _rec_name = 'shop_group_id'

    def _get_prest_partner_from_website(self, cr, uid, ids, context=None):
        prest_partner_obj = self.pool['prestashop.res.partner']
        return prest_partner_obj.search(
            cr,
            uid,
            [('shop_group_id', 'in', ids)],
            context=context
        )

    _columns = {
        'openerp_id': fields.many2one(
            'res.partner',
            string='Partner',
            required=True,
            ondelete='cascade'
        ),
        'backend_id': fields.related(
            'shop_group_id',
            'backend_id',
            type='many2one',
            relation='prestashop.backend',
            string='Prestashop Backend',
            store={
                'prestashop.res.partner': (
                    lambda self, cr, uid, ids, c=None: ids,
                    ['shop_group_id'],
                    10
                ),
                'prestashop.website': (
                    _get_prest_partner_from_website,
                    ['backend_id'],
                    20
                ),
            },
            readonly=True
        ),
        'shop_group_id': fields.many2one(
            'prestashop.shop.group',
            string='PrestaShop Shop Group',
            required=True,
            ondelete='restrict'
        ),
        'shop_id': fields.many2one(
            'prestashop.shop',
            string='PrestaShop Shop'
        ),
        'group_ids': fields.many2many(
            'prestashop.res.partner.category',
            'prestashop_category_partner',
            'partner_id',
            'category_id',
            string='PrestaShop Groups'
        ),
        'date_add': fields.datetime(
            'Created At (on PrestaShop)',
            readonly=True
        ),
        'date_upd': fields.datetime(
            'Updated At (on PrestaShop)',
            readonly=True
        ),
        'newsletter': fields.boolean('Newsletter'),
        'default_category_id': fields.many2one(
            'prestashop.res.partner.category',
            'PrestaShop default category',
            help="This field is synchronized with the field "
            "'Default customer group' in PrestaShop."
        ),
        'birthday': fields.date('Birthday'),
        'company': fields.char('Company'),
        'prestashop_address_bind_ids': fields.one2many(
            'prestashop.address', 'openerp_id',
            string="PrestaShop Address Bindings"
        ),
    }

    _sql_constraints = [
        ('prestashop_uniq', 'unique(shop_group_id, prestashop_id)',
         'A partner with the same ID on PrestaShop already exists for this '
         'website.'),
    ]


class prestashop_address(orm.Model):
    _name = 'prestashop.address'
    _inherit = 'prestashop.binding'
    _inherits = {'res.partner': 'openerp_id'}

    _rec_name = 'backend_id'

    def _get_prest_address_from_partner(self, cr, uid, ids, context=None):
        prest_address_obj = self.pool['prestashop.address']
        return prest_address_obj.search(
            cr,
            uid,
            [('prestashop_partner_id', 'in', ids)],
            context=context
        )

    _columns = {
        'openerp_id': fields.many2one(
            'res.partner',
            string='Partner',
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
        'prestashop_partner_id': fields.many2one(
            'prestashop.res.partner',
            string='Prestashop Partner',
            required=True,
            ondelete='cascade'
        ),
        'backend_id': fields.related(
            'prestashop_partner_id',
            'backend_id',
            type='many2one',
            relation='prestashop.backend',
            string='Prestashop Backend',
            store={
                'prestashop.address': (
                    lambda self, cr, uid, ids, c=None: ids,
                    ['prestashop_partner_id'],
                    10
                ),
                'prestashop.res.partner': (
                    _get_prest_address_from_partner,
                    ['backend_id', 'shop_group_id'],
                    20
                ),
            },
            readonly=True
        ),
        'shop_group_id': fields.related(
            'prestashop_partner_id',
            'shop_group_id',
            type='many2one',
            relation='prestashop.shop.group',
            string='PrestaShop Shop Group',
            store={
                'prestashop.address': (
                    lambda self, cr, uid, ids, c=None: ids,
                    ['prestashop_partner_id'],
                    10
                ),
                'prestashop.res.partner': (
                    _get_prest_address_from_partner,
                    ['shop_group_id'],
                    20
                ),
            },
            readonly=True
        ),
        'vat_number': fields.char('PrestaShop VAT'),
    }

    _sql_constraints = [
        ('prestashop_uniq', 'unique(backend_id, prestashop_id)',
         'A partner address with the same ID on PrestaShop already exists.'),
    ]


@prestashop
class ResPartnerRecordImport(PrestashopImportSynchronizer):
    _model_name = 'prestashop.res.partner'

    def _import_dependencies(self):
        groups = self.prestashop_record.get('associations', {}) \
            .get('groups', {}).get('group', [])
        if not isinstance(groups, list):
            groups = [groups]
        
        backend_adapter = self.get_connector_unit_for_model(
            BackendAdapter,
            'prestashop.product.combination.option.value'
        )
        for group in groups:
#            self._import_dependency(group['id'],
#                                   'prestashop.res.partner.category')
            import_record.delay(
                self.session,
                'prestashop.res.partner.category',
                self.backend_record.id,
                group['id']
            )

                                
                                
    def _after_import(self, erp_id):
        binder = self.get_binder_for_model(self._model_name)
        ps_id = binder.to_backend(erp_id.id)
        import_batch.delay(
            self.session,
            'prestashop.address',
            self.backend_record.id,
            filters={'filter[id_customer]': '%d' % (ps_id)},
            priority=20,
        )
