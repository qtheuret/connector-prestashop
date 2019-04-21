# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import datetime
import logging
import json

from HTMLParser import HTMLParser

from slugify import slugify

from odoo import models, fields, api, _

from odoo.addons.component.core import Component
from odoo.addons.connector.components.mapper import mapping, external_to_m2o
from odoo.addons.queue_job.job import job, related_action


_logger = logging.getLogger(__name__)
try:
    from prestapyt import PrestaShopWebServiceError
except:
    _logger.debug('Cannot import from `prestapyt`')


class ProductTemplateMapper(Component):
    _name = 'prestashop.product.template.export.mapper'
    _inherit = 'translation.prestashop.export.mapper'
    _apply_on = 'prestashop.product.template'

    _model_name = 'prestashop.product.template'

    _translatable_fields = [
        ('name', 'name'),
        ('delivery_in_stock', 'delivery_in_stock'),
        ('delivery_out_stock', 'delivery_out_stock'),
    ]

    direct = [
        ('sale_ok', 'available_for_order'),
        ('weight', 'weight'),
        ('barcode', 'ean13'),
#        ('immediately_usable_qty', 'quantity'),
    ]

    @mapping
    def additional_delivery_times(self, record):
        if record.delivery_in_stock or record.delivery_out_stock:
            return {
                'additional_delivery_times': 2,
            }
        else:
            return {'additional_delivery_times': 0}


    @mapping
    def on_sale(self, record):
        return {'on_sale': record.sale_ok and 1 or 0}

    @mapping
    def link_rewrite(self, record):
        value = {'language': []}
        records_by_lang = self._get_record_by_lang(record)
        for language_id, trans_record in records_by_lang.items():
            value['language'].append({
                'attrs': {'id': str(language_id)},
                'value': record.link_rewrite or slugify(record.name),
            })
        return {'link_rewrite': value}

    def _get_factor_tax(self, tax):
        return (1 + tax.amount / 100) if tax.price_include else 1.0

    @mapping
    def is_virtual(self, record):
        return {'is_virtual': record.type == 'service' and 1 or 0}

    @mapping
    def list_price(self, record):
        tax = record.taxes_id
        if tax.price_include and tax.amount_type == 'percent':
            # 6 is the rounding precision used by PrestaShop for the
            # tax excluded price.  we can get back a 2 digits tax included
            # price from the 6 digits rounded value
            return {
                'price': str(
                    round(record.list_price / self._get_factor_tax(tax), 6))
            }
        else:
            return {'price': str(record.list_price)}

    @mapping
    def state(self, record):
        return {'state': 1}

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
    def description(self, record):
        value = {'language': []}
        records_by_lang = self._get_record_by_lang(record)
        for language_id, trans_record in records_by_lang.items():
            _logger.debug(record.description_sale)
            h = HTMLParser()
            value['language'].append({
                'attrs': {'id': str(language_id)},
                'value': (record.description_sale and h.unescape(record.description_sale) or ''),
            })
        return {'description': value}

    @mapping
    def low_stock_alert(self, record):
        return {'low_stock_alert': 1}

    @mapping
    def wholesale_price(self, record):
        return {'wholesale_price': record.standard_price or 0.00}

    @mapping
    def id_category_default(self, record):
        if not record.categ_id:
            return {'id_category_default': 2}
        category_binder = self.binder_for('prestashop.product.category')
        ext_categ_id = category_binder.to_external(
            record.categ_id.id, wrap=True
        )
        return {
            'id_category_default': ext_categ_id,
        }

    @mapping
    def associations(self, record):
        categ_ids = []
        categ_binder = self.binder_for('prestashop.product.category')
        for categ in record.categ_ids:
            categ_id = categ_binder.to_external(
                categ.id, wrap=True
            )
            if categ_id:
                categ_ids.append({'id': categ_id})

        return {
            'associations': {
                'categories': {
                    'category': categ_ids,
                }
            },
        }

    @mapping
    def tax_ids(self, record):
        if not record.taxes_id:
            return

        binder = self.binder_for('prestashop.account.tax.group')
        ext_id = binder.to_external(record.taxes_id[:1].tax_group_id, wrap=True)
        return {'id_tax_rules_group': ext_id}

    @mapping
    def reference(self, record):
        if record.default_code:
            return {'reference': record.default_code[0:32]}

    @mapping
    def data_add(self, record):
        if record.create_date:
            return {'date_add': fields.Date.from_string(record.create_date).strftime('%Y-%m-%d %H:%M:%S')}
        else:
            return {'date_add': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

    @mapping
    def data_upd(self, record):
        if record.write_date:
            return {'date_upd': fields.Date.from_string(record.write_date).strftime('%Y-%m-%d %H:%M:%S')}
        else:
            return {'date_upd': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}


class ProductTemplateExporter(Component):
    _name = 'prestashop.product.template.exporter'
    _inherit = 'translation.prestashop.exporter'
    _apply_on = 'prestashop.product.template'
    _model_name = 'prestashop.product.template'

    def _export_dependencies(self):
        """ Export the simple delivery before export lines """
        record = self.binding and self.binding.odoo_id
        if record and record.categ_id:
            self._export_dependency(record.categ_id, 'prestashop.product.category')
