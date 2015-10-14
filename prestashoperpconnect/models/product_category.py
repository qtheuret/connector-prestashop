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
from ..unit.backend_adapter import GenericAdapter  # , PrestaShopCRUDAdapter
from ..unit.import_synchronizer import DelayedBatchImport
from ..unit.import_synchronizer import PrestashopImportSynchronizer
from ..unit.import_synchronizer import import_record
from ..unit.mapper import PrestashopImportMapper
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

    def _import_dependencies(self):
        record = self.prestashop_record
        if record['id_parent'] != '0':
            try:
                self._check_dependency(record['id_parent'],
                                       'prestashop.product.category')
            except PrestaShopWebServiceError:
                pass
            
    def tree(self, parent_id=None, storeview_id=None):
        """ Returns a tree of product categories

        :rtype: dict
        """
        def filter_ids(tree):
            children = {}
            if tree['children']:
                for node in tree['children']:
                    children.update(filter_ids(node))
            category_id = {tree['category_id']: children}
            return category_id
        if parent_id:
            parent_id = int(parent_id)
        tree = self._call('%s.tree' % self._magento_model,
                          [parent_id, storeview_id])
        return filter_ids(tree)

@prestashop
class ProductCategoryBatchImporter(DelayedBatchImport):
    """ Import the Magento Product Categories.

    For every product category in the list, a delayed job is created.
    A priority is set on the jobs according to their level to rise the
    chance to have the top level categories imported first.
    """
    _model_name = ['prestashop.product.category']

    def _import_record(self, magento_id, priority=None):
        """ Delay a job for the import """
        _logger.debug("Delay a job for the import")
        super(ProductCategoryBatchImporter, self)._import_record(
            prestashop_id, priority=priority)

    def run(self, filters=None):
        """ Run the synchronization """
        _logger.debug("RUN SYNCHRO")
        from_date = filters.pop('from_date', None)
        to_date = filters.pop('to_date', None)
        if from_date or to_date:
            updated_ids = self.backend_adapter.search(filters,
                                                      from_date=from_date,
                                                      to_date=to_date)
        else:
            updated_ids = None

        base_priority = 10

        def import_nodes(tree, level=0):
            for node_id, children in tree.iteritems():
                # By changing the priority, the top level category has
                # more chance to be imported before the childrens.
                # However, importers have to ensure that their parent is
                # there and import it if it doesn't exist
                if updated_ids is None or node_id in updated_ids:
                    self._import_record(node_id, priority=base_priority+level)
                import_nodes(children, level=level+1)
        tree = self.backend_adapter.tree()
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
