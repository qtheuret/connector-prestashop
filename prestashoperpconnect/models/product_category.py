# -*- coding: utf-8 -*-
###############################################################################
#                                                                             #
#   Prestashoperpconnect for OpenERP                                          #
#   Copyright (C) 2013 Akretion                                               #
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

import datetime
import mimetypes
import logging 
import xmlrpclib

from openerp.osv import fields, orm
from openerp import SUPERUSER_ID

from datetime import datetime
from datetime import timedelta
from prestapyt import PrestaShopWebServiceError

from ..unit.backend_adapter import (GenericAdapter, PrestaShopCRUDAdapter)
from ..unit.import_synchronizer import \
                (TranslatableRecordImport,
                DelayedBatchImport,
                )
from ..unit.mapper import (PrestashopImportMapper)
from openerp.addons.connector.connector import ConnectorUnit
from openerp.addons.connector.exception import FailedJobError
from openerp.addons.connector.exception import NothingToDoJob
from openerp.addons.connector.queue.job import job
from openerp.addons.connector.unit.synchronizer import ImportSynchronizer
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from ..backend import prestashop
from ..connector import add_checkpoint
from ..connector import get_environment
from ..unit.exception import OrderImportRuleRetry

from openerp.addons.connector.connector import Binder
from openerp.addons.connector.connector import ConnectorEnvironment
from openerp.addons.connector.deprecate import log_deprecate
from openerp.addons.connector.event import on_record_write
from openerp.addons.connector.queue.job import job
from openerp.addons.connector.unit.mapper import mapping
from openerp.addons.connector.unit.synchronizer import ExportSynchronizer
from openerp.addons.product.product import check_ean
from ..connector import get_environment
from ..unit.import_synchronizer import DelayedBatchImport
from ..unit.import_synchronizer import PrestashopImportSynchronizer
from ..unit.import_synchronizer import import_record

try:
    from xml.etree import cElementTree as ElementTree
except ImportError, e:
    from xml.etree import ElementTree

_logger = logging.getLogger(__name__)



class product_category(orm.Model):
    _inherit = 'product.category'

    _columns = {
        'prestashop_bind_ids': fields.one2many(
            'prestashop.product.category',
            'openerp_id',
            string="PrestaShop Bindings"
        ),
    }


class prestashop_product_category(orm.Model):
    _name = 'prestashop.product.category'
    _inherit = 'prestashop.binding'
    _inherits = {'product.category': 'openerp_id'}

    _columns = {
        'openerp_id': fields.many2one(
            'product.category',
            string='Product Category',
            required=True,
            ondelete='cascade'
        ),
        'default_shop_id': fields.many2one('prestashop.shop'),
        'date_add': fields.datetime(
            'Created At (on PrestaShop)',
            readonly=True
        ),
        'date_upd': fields.datetime(
            'Updated At (on PrestaShop)',
            readonly=True
        ),
        'description': fields.char('Description', translate=True),
        'link_rewrite': fields.char('Friendly URL', translate=True),
        'meta_description': fields.char('Meta description', translate=True),
        'meta_keywords': fields.char('Meta keywords', translate=True),
        'meta_title': fields.char('Meta title', translate=True),
        'active': fields.boolean('Active'),
        'position': fields.integer('Position')
    }

    _defaults = {
        'active': True
    }

#PrestashopImportSynchronizer


@prestashop
class ProductCategoryImport(TranslatableRecordImport):
    _model_name = [
        'prestashop.product.category',
    ]

    _translatable_fields = {
        'prestashop.product.category': [
            'name',
            'description',
            'link_rewrite',
            'meta_description',
            'meta_keywords',
            'meta_title'
        ],
    }        
            
    def _import_dependenciesORG(self):
        record = self.prestashop_record
        if record['id_parent'] != '0':
            try:
                self._check_dependency(record['id_parent'],
                                       'prestashop.product.category')
            except PrestaShopWebServiceError:
                pass
      

    def _import_dependenciesMGTO(self):
        """ Import the dependencies for the record"""
        record = self.prestashop_record
        # import parent category
        # the root category has a 0 parent_id
        if int(record.get('id_parent')) != 0 :
            _logger.debug("Parent found")
            parent_id = record['id_parent']
            if self.binder.to_openerp(parent_id) is None:
                importer = self.unit_for(PrestashopImportSynchronizer)
                importer.run(parent_id)

@prestashop
class ProductCategoryAdapter(GenericAdapter):
    _model_name = 'prestashop.product.category'
    _prestashop_model = 'categories'
    _export_node_name = 'category'
    
    def tree(self, parent_id=None, default_shop_id=None):
        """ Returns a tree of product categories

        :rtype: dict
        node_id : {children}
        """
        filters = {}
        tree = {}
        root = {}
                
        if parent_id:
            parent_id = int(parent_id)
            record = self.read(parent_id)
            root = {
                'category_id' : record.get('id'),
                'parent_id' : record.get('id_parent'),
                'level_depth' : record.get('level_depth'),
                'children' : []       
            }
        else :
            parent_id = 0 
            root = {
                'category_id' : 0,
                'parent_id' : None,
                'level_depth' : 0,
                'children' : []       
            }
        filters={'filter[id_parent]': '%d' % (parent_id)}
        
        for children in self.search(filters):
            record = self.read(children)
            node_id = record.get('id')
            node = {node_id : {}} 
            _logger.debug("Before node update")
            node[node_id].update(self.tree(node_id))
            tree.update(node)
        return tree

@prestashop
class ProductCategoryBatchImporter(DelayedBatchImport):
    """ Import the Magento Product Categories.

    For every product category in the list, a delayed job is created.
    A priority is set on the jobs according to their level to rise the
    chance to have the top level categories imported first.
    """
    _model_name = ['prestashop.product.category']


#    def _check_dependency(self, prestashop_id, model_name):
#        """ Use of level_depth for categories in order to prevent 
#            unsynchronized imports """
#        record = self.prestashop_record
#        prestashop_id = int(prestashop_id)
#        binder = self.get_binder_for_model(model_name)
#        priority = 0
#        if int(record['level_depth']) > 0 :
#            priority = int(record['level_depth']) -1
#        if not binder.to_openerp(prestashop_id):
#            super(ProductCategoryImport, self)._import_record(
#                                        prestashop_id, priority=priority)


    def _import_record(self, prestashop_id, priority=None):
        """ Delay a job for the import """
        super(ProductCategoryBatchImporter, self)._import_record(
            prestashop_id, priority=priority)

    def run(self, filters=None, priority=None):
        """ Run the synchronization """
        
        if filters is None:
            filters = {}
        
        filter_date = filters.pop('filter[date_upd]', None)        
        if filter_date :
            updated_ids = self.backend_adapter.search(filters)
        else:
            updated_ids = None
             
        base_priority = 10
        tree = {}               
        tree = self.backend_adapter.tree()
        
        def import_nodes(tree, level=0):
            for node_id, children in tree.iteritems():
                # By changing the priority, the top level category has
                # more chance to be imported before the childrens.
                # However, importers have to ensure that their parent is
                # there and import it if it doesn't exist
                node_id = int(node_id)                   
                if updated_ids is None or node_id in updated_ids :
                    _logger.debug("INSIDE IMPORT NODES : %s", node_id)
                    self._import_record(node_id, priority=base_priority+level)
                import_nodes(children, level=level+1)        
        import_nodes(tree)


ProductCategoryBatchImport = ProductCategoryBatchImporter  # deprecated

@prestashop
class ProductCategoryMapper(PrestashopImportMapper):
    _model_name = 'prestashop.product.category'

    direct = [
        ('position', 'sequence'),
        ('description', 'description'),
        ('link_rewrite', 'link_rewrite'),
        ('meta_description', 'meta_description'),
        ('meta_keywords', 'meta_keywords'),
        ('meta_title', 'meta_title'),
        ('id_shop_default', 'default_shop_id'),
        ('active', 'active'),
        ('position', 'position')
    ]

    @mapping
    def name(self, record):
        if record['name'] is None:
            return {'name': ''}
        return {'name': record['name']}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def parent_id(self, record):
        if record['id_parent'] == '0':
            return {}
        return {'parent_id': self.get_openerp_id(
            'prestashop.product.category',
            record['id_parent']
        )}

    @mapping
    def data_add(self, record):
        if record['date_add'] == '0000-00-00 00:00:00':
            return {'date_add': datetime.datetime.now()}
        return {'date_add': record['date_add']}

    @mapping
    def data_upd(self, record):
        if record['date_upd'] == '0000-00-00 00:00:00':
            return {'date_upd': datetime.datetime.now()}
        return {'date_upd': record['date_upd']}

    @mapping
    def default_shop_id(self, record):
        shop_group_binder = self.get_binder_for_model('prestashop.shop.group')
        default_shop_id = shop_group_binder.to_openerp(
            record['id_shop_default'])
        if not default_shop_id:
            return {}
        return {'default_shop_id': default_shop_id.id}
