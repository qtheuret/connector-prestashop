# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from openerp import models, fields, api, exceptions, _
from prestapyt import PrestaShopWebServiceError, PrestaShopWebServiceDict
from openerp.addons.connector.session import ConnectorSession
from ...unit.importer import import_batch, import_record
from ...unit.auto_matching_importer import AutoMatchingImporter
from ...connector import get_environment
from ...unit.backend_adapter import GenericAdapter, api_handle_errors, PrestaShopLocation
from ...backend import prestashop

from ..product_template.exporter import export_product_quantities
from ..product_template.importer import import_inventory
from ..res_partner.importer import import_customers_since
from ..res_partner.common import PartnerAdapter
from ..delivery_carrier.importer import import_carriers
from ..product_supplierinfo.importer import import_suppliers
from ..account_invoice.importer import import_refunds
from ..product_template.importer import import_products
from ..sale_order.importer import import_orders_since



_logger = logging.getLogger(__name__)


class PrestashopBackend(models.Model):
    _name = 'prestashop.backend'
    _description = 'PrestaShop Backend Configuration'
    _inherit = 'connector.backend'

    _backend_type = 'prestashop'

    def _select_versions(self):
        """ Available versions

        Can be inherited to add custom versions.
        """
        return [
            ('1.5', '< 1.6.0.9'),
            ('1.6.0.9', '1.6.0.9 - 1.6.0.10'),
            ('1.6.0.11', '>= 1.6.0.11'),
        ]
    version = fields.Selection(
        selection='_select_versions',
        string='Version',
        required=True,
    )
    location = fields.Char('Location')
    webservice_key = fields.Char(
        string='Webservice key',
        help="You have to put it in 'username' of the PrestaShop "
             "Webservice api path invite"
    )
    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse',
        required=True,
        help='Warehouse used to compute the stock quantities.'
    )
    taxes_included = fields.Boolean("Use tax included prices")
    quantity_field = fields.Selection(
                            [('qty_available','Available Quantity'),
                            ('virtual_available','Forecast quantity')],
                            string='Field use for quantity update',
                            required=True, 
                            default='virtual_available'
                        )
    import_partners_since = fields.Datetime('Import partners since')
    import_orders_since = fields.Datetime('Import Orders since')
    import_products_since = fields.Datetime('Import Products since')
    import_refunds_since = fields.Datetime('Import Refunds since')
    import_suppliers_since = fields.Datetime('Import Suppliers since')
    language_ids = fields.One2many(
        comodel_name='prestashop.res.lang',
        inverse_name='backend_id',
        string='Languages',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        index=True,
        required=True,
        default=lambda self: self.env['res.company']._company_default_get(
            'prestashop.backend'),
        string='Company',
    )
    discount_product_id = fields.Many2one(
        comodel_name='product.product',
        index=True,
        required=True,
        string='Discount Product',
    )
    shipping_product_id = fields.Many2one(
        comodel_name='product.product',
        index=True,
        required=True,
        string='Shipping Product',
    )
    
    #Debug and matching
    api_debug= fields.Boolean(string="Debug the API")
    
    
    matching_product_template = fields.Boolean(string="Match product template")
    
    matching_product_ch = fields.Selection([('reference','Reference'),('ean13','Barcode')],string="Matching Field for product")
    
    matching_customer = fields.Boolean(string="Matching Customer", 
                    help="The selected fields will be matched to the ref field \
                        of the partner. Please adapt your datas consequently.")
    matching_customer_ch = fields.Many2one(comodel_name='prestashop.partner.field'
                            , string="Matched field", help="Field that will be matched.")
    
    
    
    @api.model
    def create(self, vals):
        backend = super(PrestashopBackend, self).create(vals)
        if backend.location and backend.webservice_key:
            backend.fill_matched_fields(backend.id)
        return backend
    
    
    @api.onchange("matching_customer")
    def change_matching_customer(self):
        #Update the field list so that if you API change you could find the new fields to map
        if self._origin.id:
            self.fill_matched_fields(self._origin.id)
        
    
    @api.multi
    def fill_matched_fields(self, backend_id):
        self.ensure_one()
        
        options={'limit': 1,'display': 'full'}
             
        prestashop = PrestaShopLocation(
                        self.location.encode(),
                        self.webservice_key,
                    )
        
        client = PrestaShopWebServiceDict(
                    prestashop.api_url,
                    prestashop.webservice_key)

        customer = client.get('customers', options=options)
        tab=customer['customers']['customer'].keys()
        for key in tab:
            key_present = self.env['prestashop.partner.field'].search(
                    [('value', '=', key), ('backend_id', '=', backend_id)])

            if len(key_present) == 0 :
                self.env['prestashop.partner.field'].create({
                    'name' : key,
                    'value' : key,
                    'backend_id': backend_id
                })
        
    @api.multi
    def synchronize_metadata(self):
        session = ConnectorSession.from_env(self.env)
        for backend in self:
            for model in [
                'prestashop.shop.group',
                'prestashop.shop'
            ]:
                # import directly, do not delay because this
                # is a fast operation, a direct return is fine
                # and it is simpler to import them sequentially
                import_batch(session, model, backend.id)
        return True

    @api.multi
    def synchronize_basedata(self):
        session = ConnectorSession.from_env(self.env)
        for backend in self:
            for model_name in [
                'prestashop.res.lang',
                'prestashop.res.country',
                'prestashop.res.currency',
                'prestashop.account.tax',
            ]:
                env = get_environment(session, model_name, backend.id)
                directBinder = env.get_connector_unit(AutoMatchingImporter)
                directBinder.run()

            import_batch(session, 'prestashop.account.tax.group', backend.id)
            import_batch(session, 'prestashop.sale.order.state', backend.id)
        return True

    @api.multi
    def _check_connection(self):
        self.ensure_one()
        session = ConnectorSession.from_env(self.env)
        env = get_environment(session, self._name, self.id)
        adapter = env.get_connector_unit(GenericAdapter)
        with api_handle_errors('Connection failed'):
            adapter.head()

    @api.multi
    def button_check_connection(self):
        self._check_connection()
        raise exceptions.UserError(_('Connection successful'))

    @api.multi
    def import_customers_since(self):
        session = ConnectorSession.from_env(self.env)
        for backend_record in self:
            # TODO: why is it converted as user TZ?? shouldn't
            # odoo and prestashop both be UTC with ntp ?
            since_date = backend_record.import_partners_since
            import_customers_since.delay(
                session,
                backend_record.id,
                since_date=since_date,
                priority=10,
            )
        return True

    @api.multi
    def import_products(self):
        session = ConnectorSession.from_env(self.env)
        for backend_record in self:
            since_date = backend_record.import_products_since
            import_products.delay(
                session,
                backend_record.id,
                since_date,
                priority=10)
        return True

    @api.multi
    def import_carriers(self):
        session = ConnectorSession.from_env(self.env)
        for backend_record in self:
            import_carriers.delay(session, backend_record.id, priority=10)
        return True

    @api.multi
    def update_product_stock_qty(self):
        session = ConnectorSession.from_env(self.env)
        for backend_record in self:
            export_product_quantities.delay(session, backend_record.id)
        return True

    @api.multi
    def import_stock_qty(self):
        session = ConnectorSession.from_env(self.env)
        for backend_record in self:
            import_inventory.delay(session, backend_record.id)

    @api.multi
    def import_sale_orders(self):
        session = ConnectorSession.from_env(self.env)
        for backend_record in self:
            since_date = backend_record.import_orders_since
            import_orders_since.delay(
                session,
                backend_record.id,
                since_date,
                priority=5,
            )
        return True

    @api.multi
    def import_payment_modes(self):
        session = ConnectorSession.from_env(self.env)
        for backend_record in self:
            import_batch.delay(session, 'account.payment.mode',
                               backend_record.id)
        return True

    @api.multi
    def import_refunds(self):
        session = ConnectorSession.from_env(self.env)
        for backend_record in self:
            since_date = backend_record.import_refunds_since
            import_refunds.delay(session, backend_record.id, since_date)
        return True

    @api.multi
    def import_suppliers(self):
        session = ConnectorSession.from_env(self.env)
        for backend_record in self:
            since_date = backend_record.import_suppliers_since
            import_suppliers.delay(session, backend_record.id, since_date)
        return True

    def get_version_ps_key(self, key):
        keys_conversion = {
            '1.6.0.9': {
                'product_option_value': 'product_option_values',
                'category': 'categories',
                'order_slip_detail': 'order_slip_details',
                'group': 'groups',
                'order_row': 'order_rows',
                'tax': 'taxes',
                'image': 'images',
                'order_histories': 'order_histories?sendemail=1'
            },
            # singular names as < 1.6.0.9
            '1.6.0.11': {
                'product_option_value': 'product_option_values',
                'order_slip_detail': 'order_slip_details',
                'group': 'groups',
                'combination': 'combination',
                'order_row': 'order_rows',
                'tax': 'taxes',
                'image': 'image',
                'combination': 'combinations',
                'order_histories': 'order_histories?sendemail=1'},
            
            
        }
        if self.version == '1.6.0.9':
            key = keys_conversion[self.version][key]
        return key

    # TODO: new API
    def _scheduler_launch(self, cr, uid, callback, domain=None,
                          context=None):
        if domain is None:
            domain = []
        ids = self.search(cr, uid, domain, context=context)
        if ids:
            callback(cr, uid, ids, context=context)

    def _scheduler_update_product_stock_qty(self, cr, uid, domain=None,
                                            context=None):
        self._scheduler_launch(cr, uid, self.update_product_stock_qty,
                               domain=domain, context=context)

    def _scheduler_import_sale_orders(self, cr, uid, domain=None,
                                      context=None):
        self._scheduler_launch(cr, uid, self.import_sale_orders, domain=domain,
                               context=context)

    def _scheduler_import_customers(self, cr, uid, domain=None,
                                    context=None):
        self._scheduler_launch(cr, uid, self.import_customers_since,
                               domain=domain, context=context)

    def _scheduler_import_products(self, cr, uid, domain=None, context=None):
        self._scheduler_launch(cr, uid, self.import_products, domain=domain,
                               context=context)

    def _scheduler_import_carriers(self, cr, uid, domain=None, context=None):
        self._scheduler_launch(cr, uid, self.import_carriers, domain=domain,
                               context=context)

    def _scheduler_import_payment_modes(self, cr, uid, domain=None,
                                        context=None):
        self._scheduler_launch(cr, uid, self.import_payment_modes,
                               domain=domain, context=context)

        self._scheduler_launch(cr, uid, self.import_refunds,
                               domain=domain, context=context)

    def _scheduler_import_suppliers(self, cr, uid, domain=None, context=None):
        self._scheduler_launch(cr, uid, self.import_suppliers,
                               domain=domain, context=context)

    def import_record(self, cr, uid, backend_id, model_name, ext_id,
                      context=None):
        session = ConnectorSession(cr, uid, context=context)
        import_record(session, model_name, backend_id, ext_id)
        return True


class PrestashopShopGroup(models.Model):
    _name = 'prestashop.shop.group'
    _inherit = 'prestashop.binding'
    _description = 'PrestaShop Shop Group'

    name = fields.Char('Name', required=True)
    shop_ids = fields.One2many(
        comodel_name='prestashop.shop',
        inverse_name='shop_group_id',
        readonly=True,
        string="Shops",
    )
    company_id = fields.Many2one(
        related='backend_id.company_id',
        comodel_name="res.company",
        string='Company'
    )


@prestashop
class NoModelAdapter(GenericAdapter):
    """ Used to test the connection """
    _model_name = 'prestashop.backend'
    _prestashop_model = ''


@prestashop
class ShopGroupAdapter(GenericAdapter):
    _model_name = 'prestashop.shop.group'
    _prestashop_model = 'shop_groups'
    
class PrestashopPartnerField(models.Model):
    _name = 'prestashop.partner.field'
    
    name = fields.Char('Name', required=True)
    value = fields.Char('Value', required=True)
    backend_id = fields.Many2one(comodel_name="prestashop.backend", 
                string="Backend", required=True, ondelete='cascade')
