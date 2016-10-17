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
from ..unit.backend_adapter import (GenericAdapter, PrestaShopCRUDAdapter)
from ..unit.mapper import PrestashopImportMapper
from ..unit.import_synchronizer import import_record
from ..unit.import_synchronizer import (PrestashopImportSynchronizer
                                        , import_batch)
from openerp.addons.connector.connector import Binder

from openerp.addons.connector.connector import ConnectorUnit
from openerp.addons.connector.exception import FailedJobError
from openerp.addons.connector.exception import NothingToDoJob
from openerp.addons.connector.queue.job import job
from openerp.addons.connector.unit.synchronizer import ImportSynchronizer
from openerp.addons.connector.unit.backend_adapter import BackendAdapter

from openerp.addons.connector.unit.mapper import (mapping,
                                                  only_create,
                                                  ImportMapper
                                                  )                                        
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
 
    #TODO : find the problem with synchronous call of category
    # For the moment, it's reported to the _after_import
    def _import_dependencies(self):
        #Get the default category
        record = self.prestashop_record
        _logger.debug("PRESTASHOP id_default_group")
        _logger.debug(record['id_default_group'])
        self._import_dependency(record['id_default_group'],
                                   'prestashop.res.partner.category')
        # Get the list of groups
        groups = self.prestashop_record.get('associations', {}) \
            .get('groups', {}).get('group', [])
        if not isinstance(groups, list):
            groups = [groups]
        _logger.debug("IMPORT TAGS PARTNERS")
        
        
        for group in groups:
            self._import_dependency(group['id'],
                                   'prestashop.res.partner.category')
       
#            import_record(
#                self.session,
#                'prestashop.res.partner.category',
#                self.backend_record.id,
#                group['id']
#            )
#            ps_id = binder.to_backend(erp_id.id)
#            import_record.delay(
#                    self.session,
#                    'res.partner.category',
#                    self.backend_record.id,
#                    filters={'filter[id]': '%d' % (group['id'])},
#                    priority=20,
#                )
                                
                                
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
        self._set_groups_on_customer()
        
    #TODO : find the problem with synchronous call orf category    
    def _set_groups_on_customer(self):        
        partner_categories = []
        binder = self.get_binder_for_model(
                'prestashop.res.partner.category'
            )
        record = self.prestashop_record

        #Get the default category
        default_category_id = binder.to_openerp(record['id_default_group'])
        partner_categories.append(default_category_id.id)
        
        #Get the groups
        groups = record.get('associations', {}).get(
            'groups', {}).get('group', [])
        if not isinstance(groups, list):
            groups = [groups]
                
        for group in groups:
            category_id = binder.to_openerp(group['id'])
            partner_categories.append(category_id.id)

        partner_categories = list(set(partner_categories))
        #TODO [FIX]: dont seems to work in this context 
        self.env['res.partner'].write({'category_id': [(6, 0, partner_categories)]})
        
        
@prestashop
class PartnerImportMapper(PrestashopImportMapper):
    _model_name = 'prestashop.res.partner'

    direct = [
        ('date_add', 'date_add'),
        ('date_upd', 'date_upd'),
        ('email', 'email'),
        ('newsletter', 'newsletter'),
        ('company', 'company'),
        ('active', 'active'),
        ('note', 'comment'),
        ('id_shop_group', 'shop_group_id'),
        ('id_shop', 'shop_id'),
#        ('id_default_group', 'default_category_id'),
    ]

    @mapping
    def pricelist(self, record):
        binder = self.get_connector_unit_for_model(
            Binder, 'prestashop.groups.pricelist')
        pricelist_id = binder.to_openerp(
            record['id_default_group'], unwrap=True)
        if not pricelist_id:
            return {}
        return {'property_product_pricelist': pricelist_id.id}

    @mapping
    def birthday(self, record):
        if record['birthday'] in ['0000-00-00', '']:
            return {}
        return {'birthday': record['birthday']}

    @mapping
    def name(self, record):
        name = ""
        if record['firstname']:
            name += record['firstname']
        if record['lastname']:
            if len(name) != 0:
                name += " "
            name += record['lastname']
        return {'name': name}

    #TODO : find the problem with synchronous call orf category   
#    @mapping
#    def groups(self, record):
#        partner_categories = []
#        binder = self.get_binder_for_model(
#                'prestashop.res.partner.category'
#            )
#        
#        #Get the default category
#        default_category_id = binder.to_openerp(record['id_default_group'])
#        partner_categories.append(default_category_id.id)
#        
#        #Get the groups
#        groups = record.get('associations', {}).get(
#            'groups', {}).get('group', [])
#        if not isinstance(groups, list):
#            groups = [groups]
#                
#        for group in groups:
#            category_id = binder.to_openerp(group['id'])
#            partner_categories.append(category_id.id)
#
#        _logger.debug("partner_categories")
#        _logger.debug(partner_categories)
#        return {'category_id': [(6, 0, partner_categories)]}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def lang(self, record):
        binder = self.get_binder_for_model('prestashop.res.lang')
        erp_lang_id = None
        if record.get('id_lang'):
            erp_lang_id = binder.to_openerp(record['id_lang'])
        if erp_lang_id is None:
            data_obj = self.session.pool.get('ir.model.data')
            erp_lang_id = data_obj.get_object_reference(
                self.session.cr,
                self.session.uid,
                'base',
                'lang_en')[1]
        model = self.environment.session.pool.get('prestashop.res.lang')

        erp_lang = model.read(
            self.session.cr,
            self.session.uid,
            erp_lang_id.id,
        )
        return {'lang': erp_lang['code']}

    @mapping
    def customer(self, record):
        return {'customer': True}

    @mapping
    def is_company(self, record):
        # This is sad because we _have_ to have a company partner if we want to
        # store multiple adresses... but... well... we have customers who want
        # to be billed at home and be delivered at work... (...)...
        return {'is_company': True}

    @mapping
    def company_id(self, record):
        return {'company_id': self.backend_record.company_id.id}

    @mapping
    def shop_id(self, record):
        shop_binder = self.get_binder_for_model('prestashop.shop')
        shop_id = shop_binder.to_openerp(
            record['id_shop'])
        if not shop_id:
            return {}
        return {'shop_id': shop_id.id}

    @mapping
    def shop_group_id(self, record):
        shop_group_binder = self.get_binder_for_model('prestashop.shop.group')
        shop_group_id = shop_group_binder.to_openerp(
            record['id_shop_group'])
        if not shop_group_id:
            return {}
        return {'shop_group_id': shop_group_id.id}

    @mapping
    def default_category_id(self, record):
        category_binder = self.get_binder_for_model(
            'prestashop.res.partner.category')
        default_category_id = category_binder.to_openerp(
            record['id_default_group'])
        if not default_category_id:
            return {}
        return {'default_category_id': default_category_id.id}

    @mapping
    def ref(self, record):
        
        if self.backend_record.matching_customer :
            ref = record.get(self.backend_record.matching_customer_ch.value)
            if self.backend_record.matching_customer_up :
                return {'ref': ref}
        return {}

    @only_create
    @mapping
    def openerp_id(self, record):
        """ Will bind the product to an existing one with the same code """
        if self.backend_record.matching_customer:
            code = record.get(self.backend_record.matching_customer_ch.value)
            
            if code:
                partner = self.env['res.partner'].search(
                [('ref', '=', code)], limit=1)
                if partner:
                    return {'openerp_id': partner.id}
        else:
            return