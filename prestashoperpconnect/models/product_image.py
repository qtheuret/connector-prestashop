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

import logging
from openerp.osv import fields, orm

from prestapyt import PrestaShopWebServiceDict
import datetime
import mimetypes
from openerp import SUPERUSER_ID
from prestapyt import PrestaShopWebServiceDict
from openerp.addons.connector.unit.backend_adapter import CRUDAdapter
from ..backend import prestashop
from openerp.addons.connector.connector import Binder
from openerp.addons.connector.connector import ConnectorEnvironment
#from openerp.addons.connector.deprecate import log_deprecate
from openerp.addons.connector.event import on_record_write
from openerp.addons.connector.queue.job import job
from openerp.addons.connector.unit.mapper import mapping
from openerp.addons.connector.unit.synchronizer import Exporter as ExportSynchronizer

from ..connector import get_environment
from ..unit.backend_adapter import (GenericAdapter, 
                                    PrestaShopCRUDAdapter,
                                    PrestaShopWebServiceImage)
from ..unit.import_synchronizer import DelayedBatchImport
from ..unit.import_synchronizer import PrestashopImportSynchronizer
from ..unit.import_synchronizer import import_record
from ..unit.mapper import PrestashopImportMapper
try:
    from xml.etree import cElementTree as ElementTree
except ImportError, e:
    from xml.etree import ElementTree

_logger = logging.getLogger(__name__)

class product_image(orm.Model):
    _inherit = 'product.image'

    _columns = {
        'prestashop_bind_ids': fields.one2many(
            'prestashop.product.image',
            'openerp_id',
            string='PrestaShop Bindings'
        ),
    }


class prestashop_product_image(orm.Model):
    _name = 'prestashop.product.image'
    _inherit = 'prestashop.binding'
    _inherits = {'product.image': 'openerp_id'}

    _columns = {
        'openerp_id': fields.many2one(
            'product.image',
            string='Product image',
            required=True,
            ondelete='cascade'
        )
    }



# Product image connector parts
@prestashop
class ProductImageMapper(PrestashopImportMapper):
    _model_name = 'prestashop.product.image'

    direct = [
#        ('content', 'file_db_store'),
    ]

    @mapping
    def type(self, record):
#        record = record.prestashop_record
        if self.backend_record.image_store_type == 'db' :        
            type = {'file_db_store' : record['content']}
        if self.backend_record.image_store_type == 'file' :        
            #TODO : implements the correct persistence
            _logger.info("Not yet Implemented")
        if self.backend_record.image_store_type == 'url' :        
            #TODO : implements the correct persistence     
            _logger.info("Not yet Implemented")
        return type
    
    @mapping
    def template_id(self, record):
        res = self.get_openerp_id(
            'prestashop.product.template',
            record['id_product']
        )
        return {'product_id': res}

    @mapping
    def name(self, record):
        return {'name': record['id_product'] + '_' + record['id_image']}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def extension(self, record):
        return {"extension": mimetypes.guess_extension(record['type'])}


@prestashop
class ProductImageAdapter(PrestaShopCRUDAdapter):
    _model_name = 'prestashop.product.image'
    _prestashop_image_model = 'products'
    _prestashop_model = '/images/products'
    _export_node_name = '/images/products'

    def read(self, product_tmpl_id, image_id, options=None):
        api = PrestaShopWebServiceImage(self.prestashop.api_url,
                                        self.prestashop.webservice_key)
        return api.get_image(
            self._prestashop_image_model,
            product_tmpl_id,
            image_id,
            options=options
        )
    def create(self, attributes=None):
        api = PrestaShopWebServiceImage(self.prestashop.api_url,
                                        self.prestashop.webservice_key)
        template_binder = self.binder_for(
            'prestashop.product.template')
        template = template_binder.to_backend(attributes['id_product'],
                                              unwrap=True)
        url = '{}/{}'.format(self._prestashop_model,
                                template)
        #content = base64.b64encode(attributes['content'])
        return api.add(url, attributes['content'],
                       img_filename='{}.{}'.format(attributes['name'],
                       attributes['extension']))