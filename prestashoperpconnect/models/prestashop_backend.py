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

from datetime import datetime
import logging
import pytz
from ..unit.backend_adapter import GenericAdapter, PrestaShopLocation, PrestaShopWebServiceDict
from openerp.addons.connector.session import ConnectorSession
from openerp.addons.prestashoperpconnect.product import import_inventory
from openerp.osv import fields, orm
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from ..connector import get_environment
from ..unit.direct_binder import DirectBinder
from ..unit.import_synchronizer import (
    import_batch,
    import_customers_since,
    import_orders_since,
    import_products,
    import_refunds,
    import_carriers,
    import_suppliers,
    import_record,
    export_product_quantities,
)

_logger = logging.getLogger(__name__)

from openerp import models, fields as new_fields, api, exceptions, _



class prestashop_backend(orm.Model):
    _name = 'prestashop.backend'
    _doc = 'Prestashop Backend'
    _inherit = 'connector.backend'

    _backend_type = 'prestashop'


    _columns = {
        'location': fields.char('Location', required=True),
        'webservice_key': fields.char(
            'Webservice key',
            required=True,
            help="You have to put it in 'username' of the PrestaShop "
            "Webservice api path invite"
        ),
        'warehouse_id': fields.many2one(
            'stock.warehouse',
            'Warehouse',
            required=True,
            help='Warehouse used to compute the stock quantities.'
        ),
        'taxes_included': fields.boolean("Use tax included prices",
#                                         readonly=True
                                         ),
        'import_partners_since': fields.datetime('Import partners since'),
        'import_orders_since': fields.datetime('Import Orders since'),
        'import_products_since': fields.datetime('Import Products since'),
        'import_refunds_since': fields.datetime('Import Refunds since'),
        'import_suppliers_since': fields.datetime('Import Suppliers since'),
        'language_ids': fields.one2many(
            'prestashop.res.lang',
            'backend_id',
            'Languages'
        ),
        'company_id': fields.many2one('res.company', 'Company', select=1,
                                      required=True),
        'discount_product_id': fields.many2one('product.product',
                                               'Discount Product', select=1,
                                               required=False),
        'shipping_product_id': fields.many2one('product.product',
                                               'Shipping Product', select=1,
                                               required=False),
        'journal_id': fields.many2one('account.journal',
                                               'Main Journal for invoices', select=1,
                                               required=False),                                        
        'api_debug': fields.boolean("Debug the API"),
        'api_timeout': fields.float("Timeout in seconds"),
        'image_store_type' : fields.selection(
                                [('db','Database'),('file','File'),('url', 'URL')], string='Stockage type for image',
                                required=True, default='db'
                            ),
        'use_variant_default_code': fields.boolean(string='', 
                    help="""Allow to choose wether the default_code or the default variant is used"""),
        'quantity_field' : fields.selection(
                            [('qty_available','Available Quantity'),
                            ('virtual_available','Forecast quantity')],
                            string='Field use for quantity update',
                            required=True, 
                            default='virtual_available'
                        )
    }




    _defaults = {
        'company_id': lambda s, cr, uid,
        c: s.pool.get('res.company')._company_default_get(cr, uid,
                                                          'prestashop.backend',
                                                          context=c),
        'api_debug': False,
        'api_timeout': 100.0,
        'use_variant_default_code': True,
    }

    def synchronize_metadata(self, cr, uid, ids, context=None):
        if not hasattr(ids, '__iter__'):
            ids = [ids]
        session = ConnectorSession(cr, uid, context=context)
        for backend_id in ids:
            for model in ('prestashop.shop.group',
                          'prestashop.shop'):
                # import directly, do not delay because this
                # is a fast operation, a direct return is fine
                # and it is simpler to import them sequentially
                import_batch(session, model, backend_id)
        return True

    def synchronize_basedata(self, cr, uid, ids, context=None):
        if not hasattr(ids, '__iter__'):
            ids = [ids]
        session = ConnectorSession(cr, uid, context=context)
        for backend_id in ids:
            for model_name in [
                'prestashop.res.lang',
                'prestashop.res.country',
                'prestashop.res.currency',
            ]:
                env = get_environment(session, model_name, backend_id)
                directBinder = env.get_connector_unit(DirectBinder)
                directBinder.run()
            #TODO : Consider running the prestashop.configuration in asynchronous mode (Example of conf > 1000 items)
            import_batch(session, 'prestashop.configuration', backend_id)
            import_batch(session, 'prestashop.account.tax.group', backend_id)
            import_batch(session, 'prestashop.account.tax', backend_id)
            import_batch(session, 'prestashop.tax.rule', backend_id)
            import_batch(session, 'prestashop.sale.order.state', backend_id)
        return True

    def _date_as_user_tz(self, cr, uid, dtstr):
        if not dtstr:
            return None
        users_obj = self.pool.get('res.users')
        user = users_obj.browse(cr, uid, uid)
        timezone = pytz.timezone(user.partner_id.tz or 'utc')
        dt = datetime.strptime(dtstr, DEFAULT_SERVER_DATETIME_FORMAT)
        dt = pytz.utc.localize(dt)
        dt = dt.astimezone(timezone)
        return dt

    def import_customers_since(self, cr, uid, ids, context=None):
        if not hasattr(ids, '__iter__'):
            ids = [ids]
        session = ConnectorSession(cr, uid, context=context)
        for backend_record in self.browse(cr, uid, ids, context=context):
            since_date = self._date_as_user_tz(
                cr, uid, backend_record.import_partners_since
            )
            import_customers_since.delay(
                session,
                backend_record.id,
                since_date,
                priority=10,
            )

        return True

    def import_products(self, cr, uid, ids, context=None):
        if not hasattr(ids, '__iter__'):
            ids = [ids]
        session = ConnectorSession(cr, uid, context=context)
        for backend_record in self.browse(cr, uid, ids, context=context):
            since_date = self._date_as_user_tz(
                cr, uid, backend_record.import_products_since
            )
            import_products.delay(session, backend_record.id, since_date,
                                  priority=10)
        return True

    def import_carriers(self, cr, uid, ids, context=None):
        if not hasattr(ids, '__iter__'):
            ids = [ids]
        session = ConnectorSession(cr, uid, context=context)
        for backend_id in ids:
            import_carriers.delay(session, backend_id, priority=10)
        return True

    def update_product_stock_qty(self, cr, uid, ids, context=None):
        if not hasattr(ids, '__iter__'):
            ids = [ids]
        session = ConnectorSession(cr, uid, context=context)
        export_product_quantities.delay(session, ids)
        return True

    def import_stock_qty(self, cr, uid, ids, context=None):
        if not hasattr(ids, '__iter__'):
            ids = [ids]
        session = ConnectorSession(cr, uid, context=context)
        for backend_id in ids:
            import_inventory.delay(session, backend_id)

    def import_sale_orders(self, cr, uid, ids, context=None):
        if not hasattr(ids, '__iter__'):
            ids = [ids]
        session = ConnectorSession(cr, uid, context=context)
        for backend_record in self.browse(cr, uid, ids, context=context):
            since_date = self._date_as_user_tz(
                cr, uid, backend_record.import_orders_since
            )
            import_orders_since.delay(
                session,
                backend_record.id,
                since_date,
                priority=5,
            )
        return True

    def import_payment_methods(self, cr, uid, ids, context=None):
        if not hasattr(ids, '__iter__'):
            ids = [ids]
        session = ConnectorSession(cr, uid, context=context)
        for backend_record in self.browse(cr, uid, ids, context=context):
            import_batch.delay(session, 'payment.method', backend_record.id)
        return True

    def import_refunds(self, cr, uid, ids, context=None):
        if not hasattr(ids, '__iter__'):
            ids = [ids]
        session = ConnectorSession(cr, uid, context=context)
        for backend_record in self.browse(cr, uid, ids, context=context):
            since_date = self._date_as_user_tz(
                cr, uid, backend_record.import_refunds_since
            )
            import_refunds.delay(session, backend_record.id, since_date)
        return True

    def import_suppliers(self, cr, uid, ids, context=None):
        if not hasattr(ids, '__iter__'):
            ids = [ids]
        session = ConnectorSession(cr, uid, context=context)
        for backend_record in self.browse(cr, uid, ids, context=context):
            since_date = self._date_as_user_tz(
                cr, uid, backend_record.import_suppliers_since
            )
            import_suppliers.delay(session, backend_record.id, since_date)
        return True

    def _scheduler_launch(self, cr, uid, callback, domain=None,
                          context=None):
        if domain is None:
            domain = []
        ids = self.search(cr, uid, domain, context=context)
        if ids:
            callback(cr, uid, ids, context=context)

    def _scheduler_confirm_sale_orders(self, cr, uid, domain=None,
                                       context=None):
        sale_obj = self.pool.get('sale.order')
        ids = sale_obj.search(cr, uid,
                              [('state', 'in', ['draft']),
                               ('prestashop_bind_ids', '!=', False)],
                              context=context)
        for id in ids:
            sale_obj.action_button_confirm(cr, uid, id, context=context)

    def _scheduler_update_product_stock_qty(self, cr, uid, domain=None,
                                            context=None):
        self._scheduler_launch(cr, uid, self.update_product_stock_qty,
                               domain=domain, context=context)

    def _scheduler_import_sale_orders(self, cr, uid, domain=None,
                                      context=None):
        self._scheduler_launch(cr, uid, self.import_sale_orders,
                               domain=domain, context=context)

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

    def _scheduler_import_payment_methods(self, cr, uid, domain=None,
                                          context=None):
        self._scheduler_launch(cr, uid, self.import_payment_methods,
                               domain=domain, context=context)

        self._scheduler_launch(cr, uid, self.import_refunds,
                               domain=domain, context=context)

    def _scheduler_import_suppliers(self, cr, uid, domain=None, context=None):
        self._scheduler_launch(cr, uid, self.import_suppliers,
                               domain=domain, context=context)

    def _scheduler_create_payments(self, cr, uid, states=None, context=None):
        order_obj = self.pool.get('prestashop.sale.order')
        order_ids =  order_obj.search(cr, uid, [('state', 'not in', states)])
        order_obj.create_payments(cr, uid, order_ids, context=context)
            
    def import_record(self, cr, uid, backend_id, model_name, ext_id,
                      context=None):
        session = ConnectorSession(cr, uid, context=context)
        import_record(session, model_name, backend_id, ext_id)
        return True


class PrestashopPartnerField(models.Model):
    _name = 'prestashop.partner.field'
    
    name = new_fields.Char('Name', required=True)
    value = new_fields.Char('Value', required=True)
    backend_id = new_fields.Many2one(comodel_name="prestashop.backend", 
                string="Backend", required=True, ondelete='cascade')
                

class PrestashopNewAPIBackend(models.Model):
    _inherit="prestashop.backend"
    
    def _select_versions(self):
        """ Available versions

        Can be inherited to add custom versions.
        """
        return [
            ('1.5', '< 1.6.0.9'),
            ('1.6.0.9', '1.6.0.9 - 1.6.0.10'),
            ('1.6.0.11', '>= 1.6.0.11'),
        ]

    version = new_fields.Selection(
        selection='_select_versions',
        string='Version',
        required=True,
    )

    
    matching_product_template = new_fields.Boolean(string="Match product template")
    
    matching_product_ch = new_fields.Selection([('reference','Reference'),('ean13','Barcode')],string="Matching Field for product")
    
    matching_customer = new_fields.Boolean(string="Matching Customer", 
                    help="The selected fields will be matched to the ref field \
                        of the partner. Please adapt your datas consequently.")
    matching_customer_ch = new_fields.Many2one(comodel_name='prestashop.partner.field'
                            , string="Matched field", help="Field that will be matched.")
    matching_customer_up = new_fields.Boolean(string="Keep the matching filed uptodate", )
    
    trust_certificate = new_fields.Boolean("Don't validate cert and Trust Certificate", default=False)
    

    
    
    @api.model
    def create(self, vals):
        backend = super(PrestashopNewAPIBackend, self).create(vals)
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
             
             
        client = PrestaShopWebServiceDict(self.location,
                                        self.webservice_key,
                                        self.api_debug, 
#                                        None,
#                                        {'timeout': self.prestashop.api_timeout}
                                        client_args={'disable_ssl_certificate_validation': self.trust_certificate}
                                        )
                                        

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
            },
        }
        if self.version == '1.6.0.9':
            key = keys_conversion[self.version][key]
        return key

class prestashop_binding(orm.AbstractModel):
    _name = 'prestashop.binding'
    _inherit = 'external.binding'
    _description = 'PrestaShop Binding (abstract)'

    _columns = {
        # 'openerp_id': openerp-side id must be declared in concrete model
        'backend_id': fields.many2one(
            'prestashop.backend',
            'PrestaShop Backend',
            required=True,
            ondelete='restrict'),
        # TODO : do I keep the char like in Magento, or do I put a PrestaShop ?
        'prestashop_id': fields.integer('ID on PrestaShop'),
    }
    # the _sql_contraints cannot be there due to this bug:
    # https://bugs.launchpad.net/openobject-server/+bug/1151703

    def resync(self, cr, uid, ids, context=None):
        if not hasattr(ids, '__iter__'):
            ids = [ids]
        session = ConnectorSession(cr, uid, context=context)
        func = import_record
        if context and context.get('connector_delay'):
            func = import_record.delay
        for product in self.browse(cr, uid, ids, context=context):
            func(
                session,
                self._name,
                product.backend_id.id,
                product.prestashop_id
            )
        return True


# TODO remove external.shop.group from connector_ecommerce
class prestashop_shop_group(orm.Model):
    _name = 'prestashop.shop.group'
    _inherit = 'prestashop.binding'
    _description = 'PrestaShop Shop Group'

    _columns = {
        'name': fields.char('Name', required=True),
        'shop_ids': fields.one2many(
            'prestashop.shop',
            'shop_group_id',
            string="Shops",
            readonly=True),
        'company_id': fields.related('backend_id', 'company_id',
                                     type="many2one",
                                     relation="res.company",
                                     string='Company',
                                     store=False),
    }

    _sql_constraints = [
        ('prestashop_uniq', 'unique(backend_id, prestashop_id)',
         'A shop group with the same ID on PrestaShop already exists.'),
    ]


# TODO migrate from sale.shop
class prestashop_shop(orm.Model):
    _name = 'prestashop.shop'
    _inherit = 'prestashop.binding'
    _description = 'PrestaShop Shop'

    def _get_shop_from_shopgroup(self, cr, uid, ids, context=None):
        return self.pool.get('prestashop.shop').search(
            cr,
            uid,
            [('shop_group_id', 'in', ids)],
            context=context
        )

    _columns = {
        'name': fields.char('Name',
                            help="The name of the method on the backend",
                            required=True),

        'shop_group_id': fields.many2one(
            'prestashop.shop.group',
            'PrestaShop Shop Group',
            required=True,
            ondelete='cascade'
        ),
        'openerp_id': fields.many2one(
            'stock.warehouse',
            string='WareHouse',
            required=True,
            readonly=True,
            ondelete='cascade'
        ),
        # what is the exact purpose of this field?
        'default_category_id': fields.many2one(
            'product.category',
            'Default Product Category',
            help="The category set on products when?? TODO."
            "\nOpenERP requires a main category on products for accounting."
        ),
        'backend_id': fields.related(
            'shop_group_id',
            'backend_id',
            type='many2one',
            relation='prestashop.backend',
            string='PrestaShop Backend',
            store={
                'prestashop.shop': (
                    lambda self, cr, uid, ids, c={}: ids,
                    ['shop_group_id'],
                    10
                ),
                'prestashop.shop.group': (
                    _get_shop_from_shopgroup,
                    ['backend_id'],
                    20
                ),
            },
            readonly=True
        ),
        'default_url': fields.char('Default url'),
    }

    _sql_constraints = [
        ('prestashop_uniq', 'unique(backend_id, prestashop_id)',
         'A shop with the same ID on PrestaShop already exists.'),
    ]


class stock_location(orm.Model):
    _inherit = 'stock.warehouse'

    _columns = {
        'prestashop_bind_ids': fields.one2many(
            'prestashop.shop', 'openerp_id',
            string='PrestaShop Bindings',
            readonly=True),
    }


class prestashop_res_lang(orm.Model):
    _name = 'prestashop.res.lang'
    _inherit = 'prestashop.binding'
    _inherits = {'res.lang': 'openerp_id'}

    _columns = {
        'openerp_id': fields.many2one(
            'res.lang',
            string='Lang',
            required=True,
            ondelete='cascade'
        ),
        'active': fields.boolean('Active in prestashop'),
    }

    _defaults = {
        'active': False,
    }

    _sql_constraints = [
        ('prestashop_uniq', 'unique(backend_id, prestashop_id)',
         'A Lang with the same ID on Prestashop already exists.'),
    ]


class res_lang(orm.Model):
    _inherit = 'res.lang'

    _columns = {
        'prestashop_bind_ids': fields.one2many(
            'prestashop.res.lang',
            'openerp_id',
            string='prestashop Bindings',
            readonly=True),
    }


class prestashop_res_country(orm.Model):
    _name = 'prestashop.res.country'
    _inherit = 'prestashop.binding'
    _inherits = {'res.country': 'openerp_id'}

    _columns = {
        'openerp_id': fields.many2one(
            'res.country',
            string='Country',
            required=True,
            ondelete='cascade'
        ),
    }

    _sql_constraints = [
        ('prestashop_uniq', 'unique(backend_id, prestashop_id)',
         'A Country with the same ID on prestashop already exists.'),
    ]


class res_country(orm.Model):
    _inherit = 'res.country'

    _columns = {
        'prestashop_bind_ids': fields.one2many(
            'prestashop.res.country',
            'openerp_id',
            string='prestashop Bindings',
            readonly=True
        ),
    }


class prestashop_res_currency(orm.Model):
    _name = 'prestashop.res.currency'
    _inherit = 'prestashop.binding'
    _inherits = {'res.currency': 'openerp_id'}

    _columns = {
        'openerp_id': fields.many2one(
            'res.currency',
            string='Currency',
            required=True,
            ondelete='cascade'
        ),
    }

    _sql_constraints = [
        ('prestashop_uniq', 'unique(backend_id, prestashop_id)',
         'A Currency with the same ID on prestashop already exists.'),
    ]


class res_currency(orm.Model):
    _inherit = 'res.currency'

    _columns = {
        'prestashop_bind_ids': fields.one2many(
            'prestashop.res.currency',
            'openerp_id',
            string='prestashop Bindings',
            readonly=True
        ),
    }


class prestashop_account_tax(orm.Model):
    _name = 'prestashop.account.tax'
    _inherit = 'prestashop.binding'
    _inherits = {'account.tax': 'openerp_id'}

    _columns = {
        'openerp_id': fields.many2one(
            'account.tax',
            string='Tax',
            required=True,
            ondelete='cascade'
        ),
        'prestashop_tax_group_id': fields.many2one(
            'prestashop.account.tax.group',
            string='Tax Group',
            ondelete='cascade'
        ),
    }

    _sql_constraints = [
        ('prestashop_uniq', 'unique(backend_id, prestashop_id)',
         'A Tax with the same ID on prestashop already exists.'),
    ]


class account_tax(orm.Model):
    _inherit = 'account.tax'

    _columns = {
        'prestashop_bind_ids': fields.one2many(
            'prestashop.account.tax',
            'openerp_id',
            string='prestashop Bindings',
            readonly=True
        ),
    }


class prestashop_tax_rule(orm.Model):
    _name = 'prestashop.tax.rule'
    _inherit = 'prestashop.binding'
    _inherits = {'tax.rule': 'openerp_id'}

    _columns = {
        'openerp_id': fields.many2one(
            'tax.rule',
            string='Tax rule',
            required=True,
            ondelete='cascade'
        ),
        'tax_group_id': fields.many2one(
            'prestashop.account.tax.group',
            string='Tax group',
            ondelete='cascade'
        ),
        'tax_id': fields.many2one(
            'prestashop.account.tax',
            string='Tax',
            ondelete='cascade'
        ),
    }


class tax_rule(orm.Model):
    _name = 'tax.rule'

    _columns = {
        'prestashop_bind_ids': fields.one2many(
            'prestashop.tax.rule',
            'openerp_id',
            string='prestashop Bindings',
            readonly=True
        ),
        'tax_id': fields.many2one(
            'account.tax',
            string='Tax',
            #             required = True,
            ondelete='cascade'
        ),
        'tax_group_id': fields.many2one(
            'account.tax.group',
            string='Tax Group',
            #             required = True,
            ondelete='cascade'
        ),
    }


class prestashop_account_tax_group(orm.Model):
    _name = 'prestashop.account.tax.group'
    _inherit = 'prestashop.binding'
    _inherits = {'account.tax.group': 'openerp_id'}

    _columns = {
        'openerp_id': fields.many2one(
            'account.tax.group',
            string='Tax Group',
            required=True,
            ondelete='cascade'
        ),
    }

    _sql_constraints = [
        ('prestashop_uniq', 'unique(backend_id, prestashop_id)',
         'A Tax Group with the same ID on prestashop already exists.'),
    ]


class account_tax_group(orm.Model):
    _inherit = 'account.tax.group'

    _columns = {
        'prestashop_bind_ids': fields.one2many(
            'prestashop.account.tax.group',
            'openerp_id',
            string='Prestashop Bindings',
            readonly=True
        ),
        'company_id': fields.many2one(
            'res.company', 'Company', select=1,
            required=True),
    }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: