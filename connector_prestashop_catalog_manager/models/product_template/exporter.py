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
        ('meta_title', 'meta_title'),
        ('meta_description', 'meta_description'),
        ('meta_keywords', 'meta_keywords'),
    ]

    direct = [
        ('sale_ok', 'available_for_order'),
        ('weight', 'weight'),
        ('barcode', 'ean13'),
#        ('immediately_usable_qty', 'quantity'),
    ]

    @mapping
    def show_price(self, record):
        return {'show_price': record.show_price and '1' or '0'}

    @mapping
    def always_available(self, record):
        return {'active': record.always_available and '1' or '0'}

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
                'value': trans_record.link_rewrite or slugify(trans_record.name),
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
        if len(record.product_variant_ids) > 1:
            return {'price': '0.00'}
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
                'value': trans_record.name,
            })
        return {'name': value}

#    @mapping
#    @only_create
#    def description(self, record):
#        value = {'language': []}
#        records_by_lang = self._get_record_by_lang(record)
#        for language_id, trans_record in records_by_lang.items():
#            _logger.debug(trans_record.description_html)
#            h = HTMLParser()
#            value['language'].append({
#                'attrs': {'id': str(language_id)},
#                'value': (trans_record.description_html and h.unescape(trans_record.description_html) or ''),
#            })
#        return {'description': value}

    @mapping
    def dimensions(self, record):
        if record.width:
            width = record.width
        else:
            width = max([x.width or 0.00 for x in record.product_variant_ids])
        if record.height:
            height = record.height
        else:
            height = max([x.height or 0.00 for x in record.product_variant_ids])
        if record.length:
            length = record.length
        else:
            length = max([x.length or 0.00 for x in record.product_variant_ids])

        return {
            'width': width,
            'height': height,
            'depth': length,
        }

    @mapping
    def minimal_quantity(self, record):
        return {'minimal_quantity': 1}

#    @mapping
#    def low_stock_alert(self, record):
#        return {'low_stock_alert': 1}

#    @mapping
#    def wholesale_price(self, record):
#        return {'wholesale_price': record.standard_price or 0.00}

    @mapping
    def id_category_default(self, record):
        if not record.prestashop_default_category_id:
            return {'id_category_default': 2}
        category_binder = self.binder_for('prestashop.product.category')
        ext_categ_id = category_binder.to_external(
            record.prestashop_default_category_id.id, wrap=True
        )
        return {
            'id_category_default': ext_categ_id,
        }

    # @mapping
    # def associations(self, record):
    #     categ_ids = []
    #     categ_binder = self.binder_for('prestashop.product.category')
    #     for categ in record.categ_ids:
    #         categ_id = categ_binder.to_external(
    #             categ.id, wrap=True
    #         )
    #         if categ_id:
    #             categ_ids.append({'id': categ_id})
    #
    #     return {
    #         'associations': {
    #             'categories': {
    #                 'category': categ_ids,
    #             }
    #         },
    #     }

    @mapping
    def tax_ids(self, record):
        if not record.taxes_id:
            return

        binder = self.binder_for('prestashop.account.tax.group')
        ext_id = binder.to_external(record.taxes_id[:1].tax_group_id, wrap=True)
        return {'id_tax_rules_group': ext_id}

    @mapping
    def reference(self, record):
        if record.reference:
            return {'reference': record.reference}
        if record.default_code:
            return {'reference': record.default_code[0:32]}

    @mapping
    def minimal_quantity(self, record):
        return {'minimal_quantity': 1}

    @mapping
    def low_stock_alert(self, record):
        return {'low_stock_alert': 1}

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
        if record and record.prestashop_default_category_id:
            self._export_dependency(record.prestashop_default_category_id, 'prestashop.product.category')

    def _run(self, fields=None, **kwargs):
        if self.binding.prestashop_id:
            self.binding.import_record(self.binding.backend_id, self.binding.prestashop_id)
        return super(ProductTemplateExporter, self)._run(fields=fields, **kwargs)

    def _update(self, data):
        """ Update an PrestaShop record """
        assert self.prestashop_id

        id_group_shop = None
        if self.binding.id_group_shop:
            id_group_shop = self.binding.id_group_shop.prestashop_id
        else:
            id_group_shops = self.env['prestashop.shop.group'].search([('backend_id', '=', self.binding.backend_id.id)])
            if id_group_shops:
                id_group_shop = id_group_shops[0].prestashop_id

        return self.backend_adapter.write(self.prestashop_id, data, {'id_group_shop': id_group_shop})

    def _create(self, data):
        """ Create the Prestashop record """
        id_group_shop = None
        if self.binding.id_group_shop:
            id_group_shop = self.binding.id_group_shop.prestashop_id
        else:
            id_group_shops = self.env['prestashop.shop.group'].search([('backend_id', '=',
                                                                        self.binding.backend_id.id)])
            if id_group_shops:
                id_group_shop = id_group_shops[0].prestashop_id

        return self.backend_adapter.create(data, {'id_group_shop': id_group_shop})
