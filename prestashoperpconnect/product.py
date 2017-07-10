# -*- coding: utf-8 -*-
###############################################################################
#                                                                             #
#   Prestashoperpconnect for OpenERP                                          #
#   Copyright (C) 2013 Akretion                                               #
#   Copyright (C) 2015 Tech-Receptives(<http://www.tech-receptives.com>)      #
#   @author Parthiv Patel <parthiv@techreceptives.com>                        #
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

#from prestapyt import PrestaShopWebServiceDict
import datetime
import mimetypes
import logging 
from .backend import prestashop
from openerp import SUPERUSER_ID
from openerp.addons.connector.connector import Binder
from openerp.addons.connector.connector import ConnectorEnvironment
from openerp.addons.connector.deprecate import log_deprecate
from openerp.addons.connector.event import on_record_write
from openerp.addons.connector.queue.job import job, related_action
from openerp.addons.connector.unit.mapper import mapping
from openerp.addons.connector.unit.synchronizer import ExportSynchronizer
from openerp.addons.product.product import check_ean
from .connector import get_environment
from .unit.backend_adapter import GenericAdapter  # , PrestaShopCRUDAdapter
from .unit.import_synchronizer import DelayedBatchImport
from .unit.import_synchronizer import PrestashopImportSynchronizer
from .unit.import_synchronizer import import_record
from .unit.mapper import PrestashopImportMapper, only_create
from openerp.addons.connector.unit.backend_adapter import BackendAdapter
from .related_action import link

try:
    from xml.etree import cElementTree as ElementTree
except ImportError, e:
    from xml.etree import ElementTree

_logger = logging.getLogger(__name__)

########  product template ########
@prestashop
class TemplateMapper(PrestashopImportMapper):
    _model_name = 'prestashop.product.template'

    direct = [
        ('description', 'description_html'),
        ('description_short', 'description_short_html'),
        ('weight', 'weight'),
        ('wholesale_price', 'standard_price'),
        ('price', 'list_price'),
        ('id_shop_default', 'default_shop_id'),
        ('link_rewrite', 'link_rewrite'),
        ('reference', 'reference'),
        ('available_for_order', 'available_for_order'),
    ]

    @mapping
    def name(self, record):
        if record['name']:
            return {'name': record['name']}
        return {'name': 'noname'}

    @mapping
    def standard_price(self, record):
        if record['wholesale_price']:
            return {'standard_price': float(record['wholesale_price'])}
        return {}

    @mapping
    def list_price(self, record):
        taxes = self.taxes_id(record)
        # Defensive if price is null
        if not record['price'] :
            _logger.debug("Price was not found in the record. Forced to 0")
            record['price'] = '0.0'
        
        prices_and_taxes = taxes
        prices_and_taxes.update({                    
                    'list_price_tax': float(record['price'])
                })
        
        if taxes and taxes.get('taxes_id'):
            tax_id = taxes.get('taxes_id')[0][2][0]
            
            if tax_id:
                tax_model = self.session.pool.get('account.tax')
                tax = tax_model.browse(
                    self.session.cr,
                    self.session.uid,
                    tax_id,
                )
                _logger.debug("Price from record :%s and tax : %s ",record['price'],tax.amount)
                if not self.backend_record.taxes_included:
                    prices_and_taxes.update({
                        'list_price': float(record['price']) / (1 + tax.amount),
                        'final_price': float(record['price']) / (1 + tax.amount),
                    })
                else :
                    prices_and_taxes.update({
                        'list_price': float(record['price']),
                        'final_price': float(record['price']),
                    })
            
        elif record['price']:
            prices_and_taxes.update({
                'list_price': float(record['price']),                
                'final_price': float(record['price']),
            })
        
#        _logger.debug("Return prices_and_taxes")
#        _logger.debug(prices_and_taxes)
        return prices_and_taxes

    @mapping
    def date_add(self, record):
        if record['date_add'] == '0000-00-00 00:00:00':
            return {'date_add': datetime.datetime.now()}
        return {'date_add': record['date_add']}

    @mapping
    def date_upd(self, record):
        if record['date_upd'] == '0000-00-00 00:00:00':
            return {'date_upd': datetime.datetime.now()}
        return {'date_upd': record['date_upd']}

    def has_combinations(self, record):
        
        combinations = record.get('associations', {}).get(
            'combinations', {}).get('combination', [])
#        _logger.debug("len(combinations) %s" % len(combinations))
#        _logger.debug("COMBINATIONS ASSOCIATIONS %s" % record)            
        
        return len(combinations) != 0

    def _template_code_exists(self, code):
        model = self.session.pool.get('product.template')
        template_ids = model.search(self.session.cr, SUPERUSER_ID, [
            ('default_code', '=', code),
            ('company_id', '=', self.backend_record.company_id.id),
        ])
        return len(template_ids) > 0


    @only_create
    @mapping
    def openerp_id(self, record):
        """ Will bind the product to an existing one with the same code """
        print("self.backend_record.matching_product_template %s" % self.backend_record)
        print("self.backend_record.matching_product_template %s" % self.backend_record.matching_product_template)
        if self.backend_record.matching_product_template:            
            if self.has_combinations(record): 
                #Browse combinations for matching products and find if there
                #is a potential template to be matched
                
                template = self.env['product.template']
                associations = record.get('associations', {})
                combinations = associations.get('combinations', {}).get(
                                self.backend_record.get_version_ps_key('combination'), [])
                _logger.debug('Template Creation with combinations %s' % combinations)
                if len(combinations) == 1 :
                    #Defensive mode when product have no combinations, force the list mode
                    combinations = [combinations]
                for prod in combinations:
                    backend_adapter = self.unit_for(
                                BackendAdapter, 'prestashop.product.combination')
                    variant = backend_adapter.read(int(prod['id']))
                    code = variant.get(self.backend_record.matching_product_ch)
                    
                    if self.backend_record.matching_product_ch == 'reference':    
                        product = self.env['product.product'].search(
                        [('default_code', '=', code)])
                        
                        if len(product) > 1 :
                            raise ValidationError(_('Error! Multiple products ' 
                                        'found with combinations reference %s.' 
                                        'Maybe consider to update you datas') % code)
                        template |= product.product_tmpl_id
                        
                    if self.backend_record.matching_product_ch == 'ean13':
                        product = self.env['product.product'].search(
                        [('barcode', '=', code)])
                        if len(product) > 1 :
                            raise ValidationError(_('Error! Multiple products ' 
                                        'found with combinations reference %s.' 
                                        'Maybe consider to update you datas') % code)
                        template |= product.product_tmpl_id
                        
                _logger.debug('Template Matched %s' % template)
                if len(template) == 1:
                    return {'openerp_id': template.id}
                if len(template) > 1 :
                    raise ValidationError(_('Error! Multiple templates are '
                                    'found with combinations reference.'
                                    'Maybe consider to change matching option'))
            
            else:
                code = record.get(self.backend_record.matching_product_ch)
                if self.backend_record.matching_product_ch == 'reference':    
                    if code:
                        if self._template_code_exists(code):
                            product = self.env['product.template'].search(
                        [('default_code', '=', code)], limit=1)
                            if product:
                                return {'openerp_id': product.id}


                if self.backend_record.matching_product_ch == 'ean13':
                    if code:
                        product = self.env['product.template'].search(
                        [('barcode', '=', code)], limit=1)
                        if product:
                            return {'openerp_id': product.id}
        
        
        return {}

    @mapping
    def default_code(self, record):
        """ Implements different strategies for default_code of the template """
        
#        if self.backend_record.use_variant_default_code :
        _logger.debug('Use variant default code %s', self.backend_record.use_variant_default_code)
        if self.has_combinations(record)  :
#            record = record.prestashop_record
            _logger.debug("has variant so skip the code", )
            return {}
        
        code = record.get('reference')
        if not code:
            code = "backend_%d_product_%s" % (
                self.backend_record.id, record['id']
            )
        if not self._template_code_exists(code):
            return {'default_code': code}
        i = 0
#        current_code = '%s_%d' % (code, i)
        #In case of a single variant, allow to keep the default code
        current_code = '%s' % (code)
#        while self._template_code_exists(current_code):            
#            i += 1
#            if i == 1 :
#                continue
#            current_code = '%s_%d' % (code, i)
        return {'default_code': current_code}

    @mapping
    def descriptions(self, record):
        result = {}
        if record.get('description'):
            result['description_sale'] = record['description']
        if record.get('description_short'):
            result['description'] = record['description_short']
        return result

    @mapping
    def active(self, record):
        #TODO : check how the active part is set
        _logger.debug('Active of product_template')
        _logger.debug(bool(int(record['active'])))
        return {'always_available': bool(int(record['active']))}

    @mapping
    def sale_ok(self, record):
        # if this product has combinations, we do not want to sell
        # this product,
        # but its combinations (so sale_ok = False in that case).
        # sale_ok = (record['available_for_order'] == '1'
        # and not self.has_combinations(record))
        return {'sale_ok': True}

    @mapping
    def purchase_ok(self, record):
        # not self.has_combinations(record)
        return {'purchase_ok': True}

    @mapping
    def categ_id(self, record):
        if not int(record['id_category_default']):
            return
        category_id = self.get_openerp_id(
            'prestashop.product.category',
            record['id_category_default']
        )
        if category_id is not None:
            return {'categ_id': category_id}

        categories = record['associations'].get('categories', {}).get(
            self.backend_record.get_version_ps_key('category'), [])
        if not isinstance(categories, list):
            categories = [categories]
        if not categories:
            return
        category_id = self.get_openerp_id(
            'prestashop.product.category',
            categories[0]['id']
        )
        return {'categ_id': category_id}

    @mapping
    def categ_ids(self, record):
        
        categories = record['associations'].get('categories', {}).get(
            self.backend_record.get_version_ps_key('category'), [])
        if not isinstance(categories, list):
            categories = [categories]
        product_categories = []
        for category in categories:
            category_id = self.get_openerp_id(
                'prestashop.product.category',
                category['id']
            )
            product_categories.append(category_id)

        return {'categ_ids': [(6, 0, product_categories)]}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def company_id(self, record):
        return {'company_id': self.backend_record.company_id.id}

    @mapping
    def ean13(self, record):
        if self.has_combinations(record):
            return {}
        if record['ean13'] in ['', '0']:
            return {'ean13': False}
        if check_ean(record['ean13']):
            return {'ean13': record['ean13']}
        return {}


    @mapping
    def taxes_id(self, record):
        """
        Always return a tax when it's set in PS, 
        """
        if record['id_tax_rules_group'] == '0':
            return {}
        tax_group_id = self.get_openerp_id(
            'prestashop.account.tax.group',
            record['id_tax_rules_group']
        )
        if tax_group_id:
            tax_group_model = self.session.pool.get('account.tax.group')
            tax_ids = tax_group_model.read(
                self.session.cr,
                self.session.uid,
                tax_group_id,
                ['tax_ids']
            )
        result = {"taxes_id": [(6, 0, tax_ids['tax_ids'])]}
        return result


    @mapping
    def type(self, record):
        # If the product has combinations, this main product is not a real
        # product. So it is set to a 'service' kind of product. Should better
        # be a 'virtual' product... but it does not exist...
        # The same if the product is a virtual one in prestashop.
        _logger.debug("Compute the product type : %s ", record['type']['value'])
        if record['type']['value'] and record['type']['value'] == 'virtual':
            return {"type": 'service'}        
        return {"type": 'product'}

    @mapping
    def procure_method(self, record):
        if record['type'] == 'pack':
            return {
                'procure_method': 'make_to_order',
                'supply_method': 'produce',
            }
        return {}

    @mapping
    def default_shop_id(self, record):
        shop_group_binder = self.get_binder_for_model('prestashop.shop.group')
        default_shop_id = shop_group_binder.to_openerp(
            record['id_shop_default'])
        if not default_shop_id:
            return {}
        return {'default_shop_id': default_shop_id.id}


@prestashop
class TemplateAdapter(GenericAdapter):
    _model_name = 'prestashop.product.template'
    _prestashop_model = 'products'
    _export_node_name = 'product'


    def read(self, id, attributes=None):
        if attributes is None:
            attributes = {}
        
        attributes['price[price][use_tax]'] = 1
#        _logger.debug("OPTIONS PASSED IN READ %s" % attributes)
        return super(TemplateAdapter, self).read(id, attributes=attributes)

@prestashop
class ProductInventoryExport(ExportSynchronizer):
    _model_name = ['prestashop.product.template']

    def get_filter(self, template):
        binder = self.get_binder_for_model()
        prestashop_id = binder.to_backend(template.id)
        return {
            'filter[id_product]': prestashop_id,
            'filter[id_product_attribute]': 0
        }

    def run(self, binding_id, fields):
        """ Export the product inventory to Prestashop """
        template = self.session.browse(self.model._name, binding_id)
        #Refresh the values
        template.openerp_id.with_context(connector_no_export=True).update_prestashop_quantities()
        #Re-read the datas
        template = self.session.browse(self.model._name, binding_id)
        #template.
        adapter = self.get_connector_unit_for_model(
            GenericAdapter, '_import_stock_available'
        )
        filter = self.get_filter(template)
        
        adapter.export_quantity(filter, int(template.quantity))


@prestashop
class ProductInventoryBatchImport(DelayedBatchImport):
    _model_name = ['_import_stock_available']

    def run(self, filters=None, **kwargs):
        if filters is None:
            filters = {}
        filters['display'] = '[id_product,id_product_attribute]'
        return super(ProductInventoryBatchImport, self).run(filters, **kwargs)

    def _run_page(self, filters, **kwargs):
        records = self.backend_adapter.get(filters)
        for record in records['stock_availables']['stock_available']:
            self._import_record(record, **kwargs)
        return records['stock_availables']['stock_available']

    def _import_record(self, record, **kwargs):
        """ Delay the import of the records"""
        import_record.delay(
            self.session,
            '_import_stock_available',
            self.backend_record.id,
            record,
            **kwargs
        )


@prestashop
class ProductInventoryImport(PrestashopImportSynchronizer):
    _model_name = ['_import_stock_available']

    def _check_dependency(self, ext_id, model_name):
        ext_id = int(ext_id)
        binder = self.get_binder_for_model(model_name)
        if not binder.to_openerp(ext_id):
            import_record(
                self.session,
                model_name,
                self.backend_record.id,
                ext_id
            )

    def get_binder_for_model(self, model=None):
        """ Returns an new instance of the correct ``Binder`` for
        a model

        Deprecated, use ``binder_for`` now.
        """
        log_deprecate('renamed to binder_for()')
        return self.binder_for(model=model)

    def binder_for(self, model=None):
        """ Returns an new instance of the correct ``Binder`` for
        a model """
        return self.unit_for(Binder, model)

    def unit_for(self, connector_unit_class, model=None):
        """ According to the current
        :py:class:`~connector.connector.ConnectorEnvironment`,
        search and returns an instance of the
        :py:class:`~connector.connector.ConnectorUnit` for the current
        model and being a class or subclass of ``connector_unit_class``.

        If a different ``model`` is given, a new
        :py:class:`~connector.connector.ConnectorEnvironment`
        is built for this model.

        :param connector_unit_class: ``ConnectorUnit`` to search
                                     (class or subclass)
        :type connector_unit_class: :py:class:`connector.\
                                               connector.ConnectorUnit`
        :param model: to give if the ``ConnectorUnit`` is for another
                      model than the current one
        :type model: str
        """
        if model is None:
            env = self.connector_env
        else:
            env = ConnectorEnvironment(self.backend_record,
                                       self.session,
                                       model)
        return env.get_connector_unit(connector_unit_class)

    def _get_quantity(self, record):
        filters = {
            'filter[id_product]': record['id_product'],
            'filter[id_product_attribute]': record['id_product_attribute'],
            'display': '[quantity]',
        }
        quantities = self.backend_adapter.get(filters)
        all_qty = 0
        quantities = quantities['stock_availables']['stock_available']
        if isinstance(quantities, dict):
            quantities = [quantities]
        for quantity in quantities:
            all_qty += int(quantity['quantity'])

        return all_qty

    def _get_template(self, record):
        if record['id_product_attribute'] == '0':
            binder = self.get_binder_for_model('prestashop.product.template')
            return binder.to_openerp(record['id_product'], unwrap=True)
        binder = self.get_binder_for_model('prestashop.product.combination')
        return binder.to_openerp(record['id_product_attribute'], unwrap=True)

    def run(self, record):
        flag = True
        self._check_dependency(
            record['id_product'], 'prestashop.product.template')
        if record['id_product_attribute'] != '0':
            self._check_dependency(
                record['id_product_attribute'],
                'prestashop.product.combination')

        qty = self._get_quantity(record)
        if qty < 0:
            qty = 0
        template_id = self._get_template(record).id

        if record['id_product_attribute'] == '0':
            flag = False
            product_ids = self.session.pool['product.product'].search(
                self.session.cr,
                self.session.uid,
                [('product_tmpl_id', '=', template_id)],
                context=self.session.context
            )
            if len(product_ids) == 1:
                flag = True
                template_id = product_ids[0]

        if flag:
            product_qty_obj = self.session.pool['stock.change.product.qty']
            vals = {
                'location_id':
                    self.backend_record.warehouse_id.lot_stock_id.id,
                'product_id': template_id,
                'new_quantity': qty,
            }

            template_qty_id = self.session.create("stock.change.product.qty",
                                                  vals)
            context = {'active_id': template_id}
            product_qty_obj.change_product_qty(
                self.session.cr,
                self.session.uid,
                [template_qty_id],
                context=context
            )


@prestashop
class ProductInventoryAdapter(GenericAdapter):
    _model_name = '_import_stock_available'
    _prestashop_model = 'stock_availables'
    _export_node_name = 'stock_available'

    def get(self, options=None):
        api = self.connect()
        return api.get(self._prestashop_model, options=options)

    def export_quantity(self, filters, quantity):
        self.export_quantity_url(
            self.backend_record.location,
            self.backend_record.webservice_key,
            filters,
            quantity
        )

        shop_ids = self.session.search('prestashop.shop', [
            ('backend_id', '=', self.backend_record.id),
            ('default_url', '!=', False),
        ])
        shops = self.session.browse('prestashop.shop', shop_ids)
        for shop in shops:
            self.export_quantity_url(
                '%s/api' % shop.default_url,
                self.backend_record.webservice_key,
                filters,
                quantity
            )

    def export_quantity_url(self, url, key, filters, quantity):
        response = self.search(filters)        
        for stock_id in response:
            stock = self.read(stock_id)
            stock['quantity'] = int(quantity)            
            try:
                self.write(stock['id'], stock)
            except ElementTree.ParseError:
                pass


# fields which should not trigger an export of the products
# but an export of their inventory
INVENTORY_FIELDS = ('quantity',)

#    'prestashop.product.template',
@on_record_write(model_names=[
    'prestashop.product.combination'
])
def prestashop_product_stock_updated(session, model_name, record_id,
                                     fields=None):
    if session.context.get('connector_no_export'):
        return
    inventory_fields = list(set(fields).intersection(INVENTORY_FIELDS))
    if inventory_fields:
        combination = session.browse(model_name, record_id)
        backend_id = combination.backend_id
        backend_id.import_sale_orders()
        export_inventory.delay(session, model_name,
                               record_id, fields=inventory_fields,
                               priority=20)


@job
@related_action(action=link)
def export_inventory(session, model_name, record_id, fields=None):
    """ Export the inventory configuration and quantity of a product. """
    template = session.browse(model_name, record_id)
    backend_id = template.backend_id.id
    env = get_environment(session, model_name, backend_id)
    inventory_exporter = env.get_connector_unit(ProductInventoryExport)
    #import_sale_orders
    
    return inventory_exporter.run(record_id, fields)


@job
@related_action(action=link)
def import_inventory(session, backend_id):
    env = get_environment(session, '_import_stock_available', backend_id)
    inventory_importer = env.get_connector_unit(ProductInventoryBatchImport)
    return inventory_importer.run()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
