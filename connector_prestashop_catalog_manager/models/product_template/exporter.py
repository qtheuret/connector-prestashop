# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import datetime
import logging
import json

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
    ]

    direct = [
        ('sale_ok', 'available_for_order'),
#        ('immediately_usable_qty', 'quantity'),
    ]

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
            value['language'].append({
                'attrs': {'id': str(language_id)},
                'value': (record.description_sale and html.unescape(record.description_sale) or ''),
            })
        return {'description': value}

    @mapping
    def low_stock_alert(self, record):
        return {'low_stock_alert': 0}

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
    _usage = 'prestashop.product.template.exporter'
    _inherit = 'translation.prestashop.exporter'
    _apply_on = 'prestashop.product.template'
    _model_name = 'prestashop.product.template'

    def _export_dependencies(self):
        """ Export the simple delivery before export lines """
        record = self.binding and self.binding.odoo_id
        if record and record.categ_id:
            self._export_dependency(record.categ_id, 'prestashop.product.category',
                                    component_usage='prestashop.product.category.exporter')


class ProductInventoryExporter(Component):
    _name = 'prestashop.product.template.inventory.exporter'
    _inherit = 'prestashop.exporter'
    _apply_on = ['prestashop.product.template', 'prestashop.product.combination']
    _usage = 'inventory.exporter'

    def get_filter(self, template):
        binder = self.binder_for()
        prestashop_id = binder.to_external(template)
        return {
            'filter[id_product]': prestashop_id,
            'filter[id_product_attribute]': 0
         }

    def get_quantity_vals(self, template):
        return {
            'quantity': int(template.immediately_usable_qty),
            # 'out_of_stock': int(template.out_of_stock),
        }

    def run(self, template, fields):
        """ Export the product inventory to PrestaShop """
        adapter = self.component(
            usage='backend.adapter', model_name='_import_stock_available'
        )
        filter = self.get_filter(template)
        quantity_vals = self.get_quantity_vals(template)
        adapter.export_quantity(filter, quantity_vals)


class ImportInventory(models.TransientModel):
    # In actual connector version is mandatory use a model
    _name = '_import_stock_available'

    @job(default_channel='root.prestashop')
    @api.model
    def import_record(self, backend, prestashop_id, record=None, **kwargs):
        """ Import a record from PrestaShop """
        with backend.work_on(self._name) as work:
            importer = work.component(usage='record.importer')
            return importer.run(prestashop_id, record=record, **kwargs)


class ProductInventoryBatchImporter(Component):
    _name = 'prestashop._import_stock_available.batch.importer'
    _inherit = 'prestashop.delayed.batch.importer'
    _apply_on = '_import_stock_available'

    def run(self, filters=None, **kwargs):
        if filters is None:
            filters = {}
        filters['display'] = '[id,id_product,id_product_attribute]'
        _super = super(ProductInventoryBatchImporter, self)
        return _super.run(filters, **kwargs)

    def _run_page(self, filters, **kwargs):
        records = self.backend_adapter.get(filters)
        for record in records['stock_availables']['stock_available']:
            # if product has combinations then do not import product stock
            # since combination stocks will be imported
            if record['id_product_attribute'] == '0':
                combination_stock_ids = self.backend_adapter.search({
                    'filter[id_product]': record['id_product'],
                    'filter[id_product_attribute]': '>[0]',
                })
                if combination_stock_ids:
                    continue
            self._import_record(record['id'], record=record, **kwargs)
        return records['stock_availables']['stock_available']

    def _import_record(self, record_id, record=None, **kwargs):
        """ Delay the import of the records"""
        assert record
        self.env['_import_stock_available'].with_delay().import_record(
            self.backend_record,
            record_id,
            record=record,
            **kwargs
        )


class ProductInventoryImporter(Component):
    _name = 'prestashop._import_stock_available.importer'
    _inherit = 'prestashop.importer'
    _apply_on = '_import_stock_available'

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

    def _get_binding(self):
        record = self.prestashop_record
        if record['id_product_attribute'] == '0':
            binder = self.binder_for('prestashop.product.template')
            return binder.to_internal(record['id_product'])
        binder = self.binder_for('prestashop.product.combination')
        return binder.to_internal(record['id_product_attribute'])

    def _import_dependencies(self):
        """ Import the dependencies for the record"""
        record = self.prestashop_record
        self._import_dependency(
            record['id_product'], 'prestashop.product.template'
        )
        if record['id_product_attribute'] != '0':
            self._import_dependency(
                record['id_product_attribute'],
                'prestashop.product.combination'
            )

    def _check_in_new_connector_env(self):
        # not needed in this importer
        return

    def run(self, prestashop_id, record=None, **kwargs):
        assert record
        self.prestashop_record = record
        return super(ProductInventoryImporter, self).run(
            prestashop_id, **kwargs
        )

    def _import(self, binding, **kwargs):
        record = self.prestashop_record
        qty = self._get_quantity(record)
        if qty < 0:
            qty = 0
        if binding._name == 'prestashop.product.template':
            products = binding.odoo_id.product_variant_ids
        else:
            products = binding.odoo_id

        location = (self.backend_record.stock_location_id or
                    self.backend_record.warehouse_id.lot_stock_id)
        for product in products:
            vals = {
                'location_id': location.id,
                'product_id': product.id,
                'new_quantity': qty,
            }
            template_qty = self.env['stock.change.product.qty'].create(vals)
            template_qty.with_context(
                active_id=product.id,
                connector_no_export=True,
            ).change_product_qty()