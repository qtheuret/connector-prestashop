# -*- coding: utf-8 -*-
##############################################################################
#
#    Prestashoperpconnect : OpenERP-PrestaShop connector
#    Copyright (C) 2013 Akretion (http://www.akretion.com/)
#    Copyright (C) 2015 Tech-Receptives(<http://www.tech-receptives.com>)
#    Copyright 2013 Camptocamp SA
#    @author: Alexis de Lattre <alexis.delattre@akretion.com>
#    @author Sébastien BEAU <sebastien.beau@akretion.com>
#    @author: Guewen Baconnier
#    @author Parthiv Patel <parthiv@techreceptives.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

'''
A product combination is a product with different attributes in prestashop.
In prestashop, we can sell a product or a combination of a product with some
attributes.

For example, for the iPod product we can found in demo data, it has some
combinations with different colors and different storage size.

We map that in OpenERP to a product.product with an attribute.set defined for
the main product.
'''

import logging
from openerp.osv import fields, orm

from openerp.addons.connector.session import ConnectorSession

from ..unit.import_synchronizer import import_record

from prestapyt import PrestaShopWebServiceError
from ..backend import prestashop
from openerp import SUPERUSER_ID
from openerp.addons.connector.unit.backend_adapter import BackendAdapter
from openerp.addons.connector.unit.mapper import mapping
from openerp.addons.product.product import check_ean
from openerp.osv.orm import browse_record_list
from ..product import ProductInventoryExport
from ..unit.backend_adapter import GenericAdapter
from ..unit.backend_adapter import PrestaShopCRUDAdapter
from ..unit.import_synchronizer import (PrestashopImportSynchronizer,
                                        DelayedBatchImport,    
                                        TranslatableRecordImport
                                        )

from ..unit.mapper import PrestashopImportMapper

_logger = logging.getLogger(__name__)

class product_product(orm.Model):
    _inherit = 'product.product'

    _columns = {
        'prestashop_bind_ids': fields.one2many(
            'prestashop.product.combination',
            'openerp_id',
            string='PrestaShop Bindings'
        ),
        # This one is useful in order to override the template price. 
        # In PS it's not possible to find extra price from combination so we have to compute it on the fly
#        'final_price': fields.float('Final Price'),
#        'list_price_tax': fields.float('Sale Price Including Tax'),
        'default_on': fields.boolean('Default On'),
    }
    
    def _check_default_on(self, cr, uid, ids, context=None):
        for product in self.browse(cr, uid, ids, context=context):
            product_ids = self.search(cr, uid, [("default_on", "=", 1),
                                                ("product_tmpl_id", "=",
                                                 product.product_tmpl_id.id)])
            if len(product_ids) > 1:
                return False
        return True

    _constraints = [
                    (_check_default_on,
                     'Error! Only one variant can be default', ['default_on'])
                    ]

    def copy(self, cr, uid, id, default=None, context=None):
        if default is None:
            default = {}
        default['prestashop_bind_ids'] = []
        return super(product_product, self).copy(
            cr, uid, id, default=default, context=context
        )
        
    def update_prestashop_quantities(self, cr, uid, ids, context=None):
        for product in self.browse(cr, uid, ids, context=context):
            product_template = product.product_tmpl_id
            prestashop_combinations = (
                len(product_template.product_variant_ids) > 1
                and product_template.product_variant_ids) or []
            if not prestashop_combinations:
                for prestashop_product in product_template.prestashop_bind_ids:
                    prestashop_product.recompute_prestashop_qty()
            else:
                for prestashop_combination in prestashop_combinations:
                    for combination_binding in \
                            prestashop_combination.prestashop_bind_ids:
                        combination_binding.recompute_prestashop_qty()
        return True


class prestashop_product_combination(orm.Model):
    _name = 'prestashop.product.combination'
    _inherit = 'prestashop.binding'
    _inherits = {'product.product': 'openerp_id'}

    _columns = {
        'openerp_id': fields.many2one(
            'product.product',
            string='Product',
            required=True,
            ondelete='cascade'
        ),
        'main_template_id': fields.many2one(
            'prestashop.product.template',
            string='Main Template',
            required=True,
            ondelete='cascade'
        ),
        'quantity': fields.float(
            'Computed Quantity',
            help="Last computed quantity to send on Prestashop."
        ),
        'reference': fields.char('Original reference'),        
    }

    def recompute_prestashop_qty(self, cr, uid, ids, context=None):
        if not hasattr(ids, '__iter__'):
            ids = [ids]

        for product in self.browse(cr, uid, ids, context=context):
            new_qty = self._prestashop_qty(cr, uid, product, context=context)
            self.write(
                cr, uid, product.id, {'quantity': new_qty}, context=context
            )
        return True

    def _prestashop_qty(self, cr, uid, product, context=None):
        return product.qty_available



@prestashop
class ProductCombinationAdapter(GenericAdapter):
    _model_name = 'prestashop.product.combination'
    _prestashop_model = 'combinations'
    _export_node_name = 'combination'


#@prestashop
#class ProductCombinationBatchImporter(DelayedBatchImport):
#    """ Import the Magento Product Categories.
#
#    For every product category in the list, a delayed job is created.
#    A priority is set on the jobs according to their level to rise the
#    chance to have the top level categories imported first.
#    """
#    _model_name = ['prestashop.product.product']
#
#    def _import_record(self, prestashop_id, priority=None):
#        """ Delay a job for the import """
#        super(ProductCombinationBatchImporter, self)._import_record(
#            prestashop_id, priority=priority)


@prestashop
class ProductCombinationRecordImport(PrestashopImportSynchronizer):
    _model_name = 'prestashop.product.combination'
      
    def _import_dependencies(self):
        record = self.prestashop_record
        option_values = record.get('associations', {}).get(
            'product_option_values', {}).get('product_option_value', [])
        if not isinstance(option_values, list):
            option_values = [option_values]
        backend_adapter = self.get_connector_unit_for_model(
            BackendAdapter,
            'prestashop.product.combination.option.value'
        )
        for option_value in option_values:
            option_value = backend_adapter.read(option_value['id'])
            _logger.debug("OPTION VALUE in COMBINATION: " + str(option_value['id']))
#            _logger.debug(option_value)
#            self._import_dependency(
#                option_value['id_attribute_group'],
#                'prestashop.product.combination.option',
#            )
            self._import_dependency(
                option_value['id'],
                'prestashop.product.combination.option.value'
            )

                        
                        
    def unit_price_impact(self, erp_id):
        # TODO manage extra price for a combination? 
        # Really possible? https://github.com/OCA/connector-prestashop/pull/16#issuecomment-145768033 
#        main_template = self.main_template(record)
        record = self.prestashop_record
        _logger.debug("Record pour extra price")
        _logger.debug(record)
        _logger.debug(erp_id)
        unit_price_impact = float(record['unit_price_impact']) or 0.0
        _logger.debug("Unit price impact : %s ", 
                                            str(unit_price_impact))
                                            
        main_template = erp_id.product_tmpl_id
        _logger.debug("Template : %s ")
        _logger.debug(main_template)
        
        option_values = record.get('associations', {}).get(
            'product_option_values', {}).get('product_option_value', [])
        _logger.debug(option_values)
        
        for option_value_object in option_values:
#        self._get_option_value(record):
##            results.append(option_value_object.openerp_id.id)
            _logger.debug(option_value_object)
#            _logger.debug(option_value_object.name)
#            _logger.debug("Extra price : %s  "+ str(option_value_object.price_extra))

#            p_ids = self.env['product.attribute.price'].search(
#                                [('value_id', '=', option_value_object.openerp_id.id), 
#                                ('product_tmpl_id', '=', main_template.id)], 
#                                )
#            _logger.debug("Product attribute price")
#            _logger.debug(p_ids)
#            if p_ids:
#                self.session.write('product.attribute.price', p_ids, {
#                                        'price_extra': unit_price_impact}
#                                        )
#            else:
#                _logger.debug("Additionnal Price Line found")
#            
#                price_id = self.session.create('product.attribute.price', {
#                                        'product_tmpl_id': main_template.id,
#                                        'value_id': option_value_object.openerp_id.id,
#                                        'price_extra': unit_price_impact,
#                                        })
#                _logger.debug(price_id)
            
#            price_id = self.session.search('product.attribute.value',
#                                    [('product_tmpl_id', '=', main_template.id),
#                                     ('value_id', '=', option_value_object.openerp_id.id)   
#                                    ])
            
#            if price_id :
#                self.session.write(
#                        'product.attribute.price',
#                        [price_id.id],
#                        {'price_extra': float(unit_price_impact) }
#                )
        
        

#    def _after_import(self, erp_id):
#         self.unit_price_impact(erp_id)
#        record = self.prestashop_record

#ProductCombinationBatchImport = ProductCombinationBatchImporter  #deprecated

@prestashop
class ProductCombinationMapper(PrestashopImportMapper):
    _model_name = 'prestashop.product.combination'

    direct = []

    from_main = []


    @mapping
    def default_on(self, record):
        return {'default_on': bool(int(record['default_on']))}
    
    @mapping
    def image_variant(self, record):
        associations = record.get('associations', {})
        images = associations.get('images', {}).get('image', {})
        if not isinstance(images, list):
            images = [images]
        if images[0].get('id'):
            binder = self.get_binder_for_model('prestashop.product.image')
            image_id = binder.to_openerp(images[0].get('id'))
            variant_image = self.session.browse('prestashop.product.image',
                                                image_id.id)
            if variant_image:
                if variant_image.type == 'db':
                    return {'image_variant': variant_image.file_db_store}
                else:
                    adapter = self.get_connector_unit_for_model(
                        PrestaShopCRUDAdapter,
                        'prestashop.product.image')
                    try:
                        image = adapter.read(images[0].get('id'),
                                             record['value'])
                        return {'image_variant': image['content']}
                    except PrestaShopWebServiceError:
                        pass
                    except IOError:
                        pass

    #    @mapping
#    def sale_ok(self, record):
#        # if this product has combinations, we do not want to sell
#        # this product,
#        # but its combinations (so sale_ok = False in that case).
#        # sale_ok = (record['available_for_order'] == '1'
#        # and not self.has_combinations(record))
#        return {'sale_ok': True}

    @mapping
    def type(self, record):
        main_template = self.main_template(record)
        
        return {'type':main_template['type']}
    
    
    @mapping
    def product_tmpl_id(self, record):
        template = self.main_template(record)
        return {'product_tmpl_id': template.openerp_id.id}
    
    @mapping
    def list_price(self, record):
        main_template = self.main_template(record)
        prices_and_taxes = {'list_price' : main_template['list_price']}
#        record['unit_price_impact']        
#        'final_price': fields.float('Final Price'),
#        'list_price_tax': fields.float('Sale Price Including Tax'),
        
        prices_and_taxes.update({
                    "taxes_id": [(6, 0, [t.id for t in main_template['taxes_id']])]
                    })
                    
        _logger.debug(prices_and_taxes)
        _logger.debug(main_template['taxes_id'])
        return prices_and_taxes

    @mapping
    def categ_id(self, record):
        main_template = self.main_template(record)
        return {'categ_id' : main_template['categ_id'].id}
            
    @mapping
    def from_main_template(self, record):        
        main_template = self.main_template(record)
        result = {}           
        for attribute in record:
            _logger.debug("Attribute from product to be mapped : %s ", attribute)
            if attribute not in main_template:
                continue                
            if attribute == 'ean13' :
                # DOn't map the ean13 because of product_attribute
                # EAN13 and default code displayed on template are now those
                # of the default_on product
                _logger.debug("Attribute ean 13 from product won't be mapped from template")
                continue                
            if hasattr(main_template[attribute], 'id'):
                result[attribute] = main_template[attribute].id
            elif type(main_template[attribute]) is browse_record_list:
                ids = []
                for element in main_template[attribute]:
                    ids.append(element.id)
                result[attribute] = [(6, 0, ids)]
            else:
                result[attribute] = main_template[attribute]            
        return result

    def main_template(self, record):
        if hasattr(self, '_main_template'):
            return self._main_template
        template_id = self.get_main_template_id(record)
        self._main_template = self.session.browse(
            'prestashop.product.template',
            template_id.id)
        return self._main_template

    def get_main_template_id(self, record):
        template_binder = self.get_binder_for_model(
            'prestashop.product.template')
        return template_binder.to_openerp(record['id_product'])

    def _get_option_value(self, record):
        option_values = record['associations']['product_option_values'][
            'product_option_value']
        if type(option_values) is dict:
            option_values = [option_values]

        for option_value in option_values:
            option_value_binder = self.get_binder_for_model(
                'prestashop.product.combination.option.value')
            option_value_openerp_id = option_value_binder.to_openerp(
                option_value['id'])
            option_value_object = self.session.browse(
                'prestashop.product.combination.option.value',
                option_value_openerp_id.id
            )
            yield option_value_object

    @mapping
    def name(self, record):
        # revisar el estado de las caracteristicas
        template = self.main_template(record)
        options = []
        for option_value_object in self._get_option_value(record):
            key = option_value_object.attribute_id.name
            value = option_value_object.name
            options.append('%s:%s' % (key, value))
        return {'name_template': template.name}

    @mapping
    def attribute_value_ids(self, record):
        results = []
        for option_value_object in self._get_option_value(record):
            results.append(option_value_object.openerp_id.id)
        return {'attribute_value_ids': [(6, 0, results)]}

    @mapping
    def main_template_id(self, record):    
        return {'main_template_id': self.get_main_template_id(record).id}

    def _template_code_exists(self, code):
        model = self.session.pool.get('product.product')
        combination_binder = self.get_binder_for_model('prestashop.product.combination')
        template_ids = model.search(self.session.cr, SUPERUSER_ID, [
            ('default_code', '=', code),
            ('company_id', '=', self.backend_record.company_id.id),
        ])
#        return len(template_ids) > 0
        return template_ids and not combination_binder.to_backend(template_ids,
                                                                  unwrap=True)

    @mapping
    def default_code(self, record):        
        code = record.get('reference')
        if not code:
            code = "%s_%s" % (record['id_product'], record['id'])
        if not self._template_code_exists(code):
            return {'default_code': code}
        i = 1
        current_code = '%s_%s' % (code, i)
        while self._template_code_exists(current_code):
            i += 1
            current_code = '%s_%s' % (code, i)
        return {'default_code': current_code}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def ean13(self, record): 
        if record['ean13'] in ['', '0']:
            backend_adapter = self.get_connector_unit_for_model(
                GenericAdapter, 'prestashop.product.template')
            template = backend_adapter.read(record['id_product'])
            return template['ean13'] and {}
        if check_ean(record['ean13']):   
            return {'ean13': record['ean13']}                
        return {}

    # DIMENSION PART, depends on product dimension
    
    @mapping
    def length(self, record):          
        backend_adapter = self.get_connector_unit_for_model(
                GenericAdapter, 'prestashop.product.template')
        main_template = backend_adapter.read(record['id_product'])
        return {'length': main_template['depth']}
    
    @mapping
    def height (self, record):
        backend_adapter = self.get_connector_unit_for_model(
                GenericAdapter, 'prestashop.product.template')
        main_template = backend_adapter.read(record['id_product'])
        return {'height': main_template['height']}
    
    @mapping
    def width(self, record):  
        backend_adapter = self.get_connector_unit_for_model(
                GenericAdapter, 'prestashop.product.template')
        main_template = backend_adapter.read(record['id_product'])
        return {'width': main_template['width']}
    

# COMBINATION OPTIONS AND VALUES    
    
class product_attribute(orm.Model):
    _inherit = 'product.attribute'

    _columns = {
        'prestashop_bind_ids': fields.one2many(
            'prestashop.product.combination.option',
            'openerp_id',
            string='PrestaShop Bindings (combinations)'
        ),
    }


class prestashop_product_combination_option(orm.Model):
    _name = 'prestashop.product.combination.option'
    _inherit = 'prestashop.binding'
    _inherits = {'product.attribute': 'openerp_id'}

    _columns = {
        'openerp_id': fields.many2one(
            'product.attribute',
            string='Attribute',
            required=True,
            ondelete='cascade'
        ),
        'prestashop_position': fields.integer('Prestashop Position'),
        'group_type': fields.selection([('color', 'Color'),
                                        ('radio', 'Radio'),
                                        ('select', 'Select')], 'Type'),
        'public_name': fields.char(
            'Public Name',
            translate=True
        ),

    }
    
    _sql_constraints = [
        ('prestashop_unique_option', 'unique(backend_id, prestashop_id)',
         'An attribute with the same ID on PrestaShop already exists.'),
    ]

    _defaults = {
        'group_type': 'select',
    }


class product_attribute_value(orm.Model):
    _inherit = 'product.attribute.value'

    _columns = {
        'prestashop_bind_ids': fields.one2many(
            'prestashop.product.combination.option.value',
            'openerp_id',
            string='PrestaShop Bindings'
        ),
    }


class prestashop_product_combination_option_value(orm.Model):
    _name = 'prestashop.product.combination.option.value'
    _inherit = 'prestashop.binding'
    _inherits = {'product.attribute.value': 'openerp_id'}

    _columns = {
        'openerp_id': fields.many2one(
            'product.attribute.value',
            string='Attribute',
            required=True,
            ondelete='cascade'
        ),
        'prestashop_position': fields.integer('Prestashop Position'),
#        'id_attribute_group': fields.many2one(
#            'prestashop.product.combination.option', required=True)
        'id_attribute_group': fields.many2one(
            'product.attribute',
            string='Attribute',
            required=True,   
            ondelete='cascade'
        ),
    }

    _sql_constraints = [
        ('prestashop_unique_option', 'unique(backend_id, prestashop_id)',
         'An attribute with the same ID on PrestaShop already exists.'),
    ]
    
    _defaults = {
        'prestashop_position': 1
    }

    def create(self, cr, uid, vals, context=None):      
        _logger.debug("VALUES TO INSERT")
        _logger.debug(vals)
        return super(prestashop_product_combination_option_value, self).create(
            cr, uid, vals, context=context
        )


@prestashop
class ProductCombinationOptionAdapter(GenericAdapter):
    _model_name = 'prestashop.product.combination.option'
    _prestashop_model = 'product_options'
    _export_node_name = 'product_options'


@prestashop
class ProductCombinationOptionRecordImport(PrestashopImportSynchronizer):
    _model_name = 'prestashop.product.combination.option'

    def _import_values(self):
        record = self.prestashop_record
        option_values = record.get('associations', {}).get(
            'product_option_values', {}).get('product_option_value', [])
        if not isinstance(option_values, list):
            option_values = [option_values]
        for option_value in option_values:
#            self._check_dependency(
#                option_value['id'],
#                'prestashop.product.combination.option.value'
#            )
            _logger.debug("IMPORT VALUE : ")
            _logger.debug(option_value)
            self._import_dependency(
                option_value['id'],
                'prestashop.product.combination.option.value'
            )
    
#    def _after_import(self, ext_id):
#        _logger.debug("AFTER IMPORT")
#        self._import_values()
        
    def run(self, ext_id):
        # looking for an product.attribute with the same name
        # TODO : improve the searche because there are some duplicate values
        self.prestashop_id = ext_id
        self.prestashop_record = self._get_prestashop_data()
        
        _logger.debug("OPTION IMPORT")
        #Check wether the option is already in db
        binder = self.get_binder_for_model(
            'prestashop.product.combination.option')
        attribute_id = binder.to_openerp(ext_id, unwrap=True)
        
        if len(attribute_id) == 1:
            _logger.debug("Attribute %s already exists ", (attribute_id))
            return self.prestashop_record
        
        #Search on name if there wasn't already an option
        name = self.mapper.name(self.prestashop_record)['name']
        attribute_ids = self.session.search('product.attribute',
                                            [('name', '=', name)])
        
        if len(attribute_ids) == 0:
            # if we don't find it, we create a prestashop_product_combination
            super(ProductCombinationOptionRecordImport, self).run(ext_id)
        else:
            # else, we create only a prestashop.product.combination.option
            data = {
                'openerp_id': attribute_ids[0],
                'backend_id': self.backend_record.id,
            }
            erp_id = self.model.create(data)
            self.binder.bind(self.prestashop_id, erp_id)

#        self._import_values()
             
             
@prestashop
class ProductCombinationOptionMapper(PrestashopImportMapper):
    _model_name = 'prestashop.product.combination.option'

    direct = []

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def name(self, record):
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
class ProductCombinationOptionValueAdapter(GenericAdapter):
    _model_name = 'prestashop.product.combination.option.value'
    _prestashop_model = 'product_option_values'
    _export_node_name = 'product_option_value'


@prestashop
class ProductCombinationOptionValueRecordImport(TranslatableRecordImport):
    _model_name = 'prestashop.product.combination.option.value'

    _translatable_fields = {
        'prestashop.product.combination.option.value': ['name'],
    }
    
#@prestashop
#class ProductCombinationOptionValueRecordImport(PrestashopImportSynchronizer):
#    _model_name = 'prestashop.product.combination.option.value'
#    
    def _import_dependencies(self):
        _logger.debug("Option value dependency")
        #Get the default category
        record = self.prestashop_record
        _logger.debug(record)
        self._import_dependency(record['id_attribute_group'],
                                   'prestashop.product.combination.option')


@prestashop
class ProductCombinationOptionValueMapper(PrestashopImportMapper):
    _model_name = 'prestashop.product.combination.option.value'

    direct = []

    @mapping
    def name(self, record):
        #TODO : improve the search to prevent duplicates
        name = None
        binder = self.get_binder_for_model(
            'prestashop.product.combination.option')
        attribute_id = binder.to_openerp(record['id_attribute_group'],
                                         unwrap=True)
        _logger.debug("ATRIBUTE ID to filter on : ")
        _logger.debug(attribute_id)
        #Precise the filter so that the name searched appears for a specific attribute
        search_params = [('name', '=', record['name'])
                        ,('attribute_id', '=', attribute_id.id)]
        duplicate_name = self.session.search('product.attribute.value',
                                            search_params)
        name = record['name']
        
        
        if duplicate_name:
            name = "%s-%s" % (record['name'], record['id'])
        else:
            name = record['name']
        _logger.debug("Duplicate name")
        _logger.debug(duplicate_name)
        _logger.debug(name)
        return {'name': name}

    @mapping
    def attribute_id(self, record):
        binder = self.get_binder_for_model(
            'prestashop.product.combination.option')
        attribute_id = binder.to_openerp(record['id_attribute_group'],
                                         unwrap=True)
        _logger.debug("ATRIBUTE ID FIND : ")
        _logger.debug(attribute_id)
        return {'attribute_id': attribute_id.id,
               'id_attribute_group': attribute_id.id 
               }

#    @mapping
#    def price_extra(self, record):
#        # TODO manage extra price from template        
##        main_template = self.main_template(record)
##        unit_price_impact = float(record['unit_price_impact']) or 0.0
##        _logger.debug("Unit price impact : %s ", 
##                                            str(unit_price_impact))
##        _logger.debug("Price from template : %s ", 
##                                            str(main_template['list_price']))
#                                            
#        _logger.debug("Mapping price extra")
#        _logger.debug(record)
#        return {}
    

    
    
    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}


@prestashop
class CombinationInventoryExport(ProductInventoryExport):
    _model_name = ['prestashop.product.combination']

    def get_filter(self, template):
        return {
            'filter[id_product]': template.main_template_id.prestashop_id,
            'filter[id_product_attribute]': template.prestashop_id,
        }

