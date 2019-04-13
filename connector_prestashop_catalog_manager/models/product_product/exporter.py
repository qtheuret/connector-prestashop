# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import datetime
import logging

from odoo import fields, _

from odoo.addons.component.core import Component
from odoo.addons.connector.components.mapper import mapping, external_to_m2o

_logger = logging.getLogger(__name__)
try:
    from prestapyt import PrestaShopWebServiceError
except:
    _logger.debug('Cannot import from `prestapyt`')


class ProductProductExportMapper(Component):
    _name = 'prestashop.product.combination.export.mapper'
    _inherit = 'translation.prestashop.export.mapper'
    _apply_on = 'prestashop.product.combination'

    _model_name = 'prestashop.product.combination'

    _translatable_fields = [
    ]

    direct = [
        ('price', 'list_price'),
    ]

    @mapping
    def wholesale_price(self, record):
        return {'wholesale_price': record.standard_price or 0.00}

    @mapping
    def reference(self, record):
        if record.default_code:
            return {'reference': record.default_code[0:32]}

    @mapping
    def name(self, record):
        value = {'language': []}
        records_by_lang = self._get_record_by_lang(record)
        for language_id, trans_record in records_by_lang.items():
            value['language'].append({
                'attrs': {'id': str(language_id)},
                'value': record.name,
            })
        return {'name': value}

    def get_main_template_id(self, record):
        for binding in record.product_tmpl_id.prestashop_bind_ids.filtered(
                lambda a: a.backend_id.id == self.backend_record.id):
            return binding.id

        return False

    @mapping
    def main_template_id(self, record):
        return {'main_template_id': self.get_main_template_id(record)}

    @mapping
    def id_product(self, record):
        if not record.product_tmpl_id:
            return {'id_product': 2}
        product_binder = self.binder_for('prestashop.product.template')
        ext_product_id = product_binder.to_external(
            record.product_tmpl_id.id, wrap=True
        )
        return {
            'id_product': ext_product_id,
        }

    @mapping
    def associations(self, record):
        if not record.attribute_value_ids:
            return {'associations': False}

        option_value = []
        option_name = []
        attr_values_binder = self.binder_for('prestashop.product.combination.option.value')
        for attr in record.attribute_value_ids:
            value_id = attr_values_binder.to_external(
                attr.id, wrap=True
            )
            if value_id:
                option_value.append({'id': value_id})
                option_name.append(attr.name)

        return {
            'associations': {
                'product_option_values': {
                    'product_option_value': option_value,
                }
            },
            'reference': record.default_code or ' '.join(x for x in option_name),
        }

    @mapping
    def minimal_quantity(self, record):
        return {'minimal_quantity': 1}

    @mapping
    def low_stock_alert(self, record):
        return {'low_stock_alert': 1}


class ProductProductExporter(Component):
    _name = 'prestashop.product.combination.exporter'
    _inherit = 'translation.prestashop.exporter'
    _apply_on = 'prestashop.product.combination'
    _model_name = 'prestashop.product.combination'

    def _export_dependencies(self):
        """ Export the simple delivery before export lines """
        record = self.binding and self.binding.odoo_id
        if record and record.product_tmpl_id:
            self._export_dependency(record.product_tmpl_id, 'prestashop.product.template',
                                    component_usage='prestashop.product.template.exporter')

        if record and record.attribute_value_ids:
            for attr in record.attribute_value_ids:
                self._export_dependency(attr, 'prestashop.product.combination.option.value',
                                        component_usage='prestashop.product.combination.option.value.exporter')


class ProductAttributeMapper(Component):
    _name = 'prestashop.product.combination.option.export.mapper'
    _inherit = 'translation.prestashop.export.mapper'
    _apply_on = 'prestashop.product.combination.option'

    _model_name = 'prestashop.product.combination.option'

    _translatable_fields = [
        ('name', 'name'),
        ('name', 'public_name'),
    ]

    direct = [
        # is_color_group
        # position
    ]

    @mapping
    def group_type(self, record):
        return {'group_type': 'select'}

    @mapping
    def name(self, record):
        value = {'language': []}
        records_by_lang = self._get_record_by_lang(record)
        for language_id, trans_record in records_by_lang.items():
            value['language'].append({
                'attrs': {'id': str(language_id)},
                'value': record.name,
            })
        return {'name': value}

    @mapping
    def public_name(self, record):
        value = {'language': []}
        records_by_lang = self._get_record_by_lang(record)
        for language_id, trans_record in records_by_lang.items():
            value['language'].append({
                'attrs': {'id': str(language_id)},
                'value': record.name,
            })
        return {'public_name': value}

    @mapping
    def data_add(self, record):
        if record.create_date:
            return {'date_add': fields.Datetime.from_string(record.create_date).strftime('%Y-%m-%d %H:%M:%S')}
        else:
            return {'date_add': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

    @mapping
    def data_upd(self, record):
        if record.write_date:
            return {'date_upd': fields.Datetime.from_string(record.write_date).strftime('%Y-%m-%d %H:%M:%S')}
        else:
            return {'date_upd': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}


class ProductAttributeExporter(Component):
    _name = 'prestashop.product.combination.option.exporter'
    _inherit = 'translation.prestashop.exporter'
    _apply_on = 'prestashop.product.combination.option'
    _model_name = 'prestashop.product.combination.option'


class ProductAttributeValueMapper(Component):
    _name = 'prestashop.product.combination.option.value.export.mapper'
    _inherit = 'translation.prestashop.export.mapper'
    _apply_on = 'prestashop.product.combination.option.value'

    _model_name = 'prestashop.product.combination.option.value'

    _translatable_fields = [
        ('name', 'name'),
    ]

    direct = [
    ]

    @mapping
    def name(self, record):
        value = {'language': []}
        records_by_lang = self._get_record_by_lang(record)
        for language_id, trans_record in records_by_lang.items():
            value['language'].append({
                'attrs': {'id': str(language_id)},
                'value': record.name,
            })
        return {'name': value}

    @mapping
    def id_attribute_group(self, record):
        if not record.attribute_id:
            return {'id_attribute_group': 2}
        category_binder = self.binder_for('prestashop.product.combination.option')
        ext_attr_id = category_binder.to_external(
            record.attribute_id.id, wrap=True
        )
        return {
            'id_attribute_group': ext_attr_id,
        }


class ProductAttributeValueExporter(Component):
    _name = 'prestashop.product.combination.option.value.exporter'
    _inherit = 'translation.prestashop.exporter'
    _apply_on = 'prestashop.product.combination.option.value'
    _model_name = 'prestashop.product.combination.option.value'

    def _export_dependencies(self):
        """ Export the simple delivery before export lines """
        record = self.binding and self.binding.odoo_id
        if record and record.attribute_id:
            self._export_dependency(record.attribute_id, 'prestashop.product.combination.option',
                                    component_usage='prestashop.product.combination.option.exporter')
