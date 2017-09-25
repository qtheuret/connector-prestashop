# -*- coding: utf-8 -*-
###############################################################################
#                                                                             #
#   Prestashoperpconnect for OpenERP                                          #
#   Copyright (C) 2013 Akretion                                               #
#   Copyright (C) 2015 Tech-Receptives(<http://www.tech-receptives.com>)
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

import logging
import openerp.addons.decimal_precision as dp
import logging
from prestapyt import PrestaShopWebServiceDict
from ..backend import prestashop
from openerp.addons.connector.event import on_record_write
from openerp.addons.connector.queue.job import job
from openerp.addons.connector.connector import ConnectorUnit
from openerp.addons.connector.session import ConnectorSession

from openerp.addons.connector.unit.synchronizer import (ExportSynchronizer)
from openerp.addons.connector_ecommerce.unit.sale_order_onchange import (
    SaleOrderOnChange)
from ..connector import get_environment
from ..unit.backend_adapter import GenericAdapter
from ..unit.import_synchronizer import SaleImportRule
from ..unit.backend_adapter import GenericAdapter

#from openerp.osv import fields, orm
from openerp import models, fields, api, _

_logger = logging.getLogger(__name__)

class sale_order_state(models.Model):
    _name = 'sale.order.state'
    
    name = fields.Char('Name', size=128, translate=True)
    company_id = fields.Many2one(comodel_name='res.company', 
                                string='Company', required=True)
    prestashop_bind_ids = fields.One2many(
                                comodel_name='prestashop.sale.order.state',
                                inverse_name='openerp_id',
                                string="Prestashop Bindings"
                                )

    


class prestashop_sale_order_state(models.Model):
    _name = 'prestashop.sale.order.state'
    _inherit = 'prestashop.binding'
    _inherits = {'sale.order.state': 'openerp_id'}

    openerp_state_ids=fields.One2many(
            comodel_name='sale.order.state.list',
            inverse_name='prestashop_state_id',
            string='OpenERP States'
        )
    openerp_id = fields.Many2one(
            comodel_name='sale.order.state',
            string='Sale Order State',
            required=True,
            ondelete='cascade'
        )
    

class sale_order_state_list(models.Model):
    _name = 'sale.order.state.list'

    name = fields.Selection(
            [
                ('draft', 'Draft Quotation'),
                ('sent', 'Quotation Sent'),
                ('cancel', 'Cancelled'),
                ('waiting_date', 'Waiting Schedule'),
                ('progress', 'Sales Order'),
                ('manual', 'Sale to Invoice'),
                ('invoice_except', 'Invoice Exception'),
                ('done', 'Done'),
            ],
            string='OpenERP State',
            required=True
        )
    prestashop_state_id = fields.Many2one(
            comodel_name='prestashop.sale.order.state',
            string='Prestashop State'
        )
    prestashop_id = fields.Integer(
            related='prestashop_state_id.prestashop_id',
            string='Prestashop ID',            
            readonly=True,
            store=True
        )
    

class sale_order(models.Model):
    _inherit = 'sale.order'

    prestashop_bind_ids = fields.One2many(
            comodel_name='prestashop.sale.order', 
            inverse_name='openerp_id',            
            string="Prestashop Bindings"
        )
    
    prestashop_order_id = fields.Integer(
                    related="prestashop_bind_ids.prestashop_id", 
                    store=True, 
                    string="Order_id On prestashop",
                    default=False,
                    index=True)
    
    prestashop_invoice_number = fields.Char(
                    related="prestashop_bind_ids.prestashop_invoice_number",
                    store=False,
                    string="Invoice Number",
        
                    )
                    
    main_picking = fields.Char(
            related='picking_ids.name',
#            comodel_name="stock.picking", 
            string='Main picking',            
            readonly=True,
            store=True
        )
    
    @api.multi
    def action_invoice_create(self, grouped=False, states=['confirmed', 'done', 'exception'], date_invoice = False, context=None):
        """In order to follow the invoice number of prestashop, 
        all the invoices generated from this workflow have to be tagged 
        with the prestashop_invoice_number
        In case of the invoice is not generated mainly from PS (eg : workflow accept invoice unpaid)
        the prestashop_invoice_number will be empty and won't cause troubles, 
        the usual invoice number associated to the journal will be used.
        """
        res = super(sale_order,self).action_invoice_create(grouped=grouped, states=states, date_invoice = date_invoice, context=context)
        
            
        if isinstance(res, int):       
            #it can't be a grouped invoice creation so deal with that
            inv_ids = self.env['account.invoice'].browse([res])
            new_name = self.name
            if self.prestashop_order_id and self.prestashop_order_id > 0 :
                new_name = `self.prestashop_order_id` + '-'+  new_name                    
                inv_ids.write({'internal_number' :self.prestashop_invoice_number,
                            'origin' : new_name,
                            })
        
        if len(self.prestashop_bind_ids) == 1 and self.prestashop_bind_ids[0].backend_id.journal_id.id :
            #we also have to set the journal for the invoicing only for 
            #orders coming from the connector
            inv_ids.write({'journal_id':
                        self.prestashop_bind_ids[0].backend_id.journal_id.id })
            
            
        return res
    
    @api.v7
    def _prepare_procurement_group(self, cr, uid, order, context=None):   
        #Improve the origin of shipping and name of the procurement group for better tracability
        new_name = order.name 
        if order.prestashop_order_id > 0 :
            new_name = `order.prestashop_order_id` + '-' + new_name        
        return {'name': new_name , 'partner_id': order.partner_shipping_id.id}
    
    @api.v7
    def _prepare_order_line_procurement(self, cr, uid, order, line, group_id=False, context=None):
        #Improve the origin of shipping and name of the procurement group for better tracability
        new_name = order.name
        if order.prestashop_order_id > 0 :
            new_name = `order.prestashop_order_id` + '-'+  new_name
        vals = super(sale_order, self)._prepare_order_line_procurement(cr, uid, order, line, group_id=group_id, context=context)        
        vals['origin'] = new_name
        return vals
        

class prestashop_sale_order(models.Model):
    _name = 'prestashop.sale.order'
    _inherit = 'prestashop.binding'
    _inherits = {'sale.order': 'openerp_id'}

   
    openerp_id = fields.Many2one(
            comodel_name = 'sale.order',
            string='Sale Order',
            required=True,
            ondelete='cascade'
            )
    prestashop_order_line_ids = fields.One2many(
            comodel_name = 'prestashop.sale.order.line',
            inverse_name = 'prestashop_order_id',
            string = 'Prestashop Order Lines'
        )
    prestashop_discount_line_ids = fields.One2many(
            comodel_name = 'prestashop.sale.order.line.discount',
            inverse_name = 'prestashop_order_id',
            string = 'Prestashop Discount Lines'
            )
    prestashop_invoice_number = fields.Char(
            string = 'PrestaShop Invoice Number', size=64
            )
    prestashop_delivery_number = fields.Char(
            string = 'PrestaShop Delivery Number', size=64
        )
    total_amount = fields.Float(
            string = 'Total amount in Prestashop',
            digits_compute=dp.get_precision('Account'),
            readonly=True
        )
    total_amount_tax = fields.Float(
            string = 'Total tax in Prestashop',
            digits_compute=dp.get_precision('Account'),
            readonly=True
        )
    total_shipping_tax_included = fields.Float(
            string = 'Total shipping in Prestashop',
            digits_compute=dp.get_precision('Account'),
            readonly=True
        )
    total_shipping_tax_excluded = fields.Float(
            string = 'Total shipping in Prestashop',
            digits_compute=dp.get_precision('Account'),
            readonly=True
        )
    
    @api.model
    def create_payments(self, ps_orders):
        _logger.debug("CREATE PAYMENTS")
        _logger.debug(ps_orders)
        
        for order in self.browse(ps_orders ):
            _logger.debug("CHECK for order %s with id %s" % (order.name, order.openerp_id.id))     
#            if order.openerp_id.id != 88:
#                continue
                                           
            session = ConnectorSession(self.env.cr, self.env.uid,
                                   context=self.env.context)
            backend_id = order.backend_id
            env = get_environment(session, 'prestashop.sale.order', backend_id.id)
            _logger.debug(env)
            
            adapter = env.get_connector_unit(SaleOrderAdapter)
            ps_order = adapter.read(order.prestashop_id)
            #Force the rules check
            rules = env.get_connector_unit(SaleImportRule)
            rules.check(ps_order)
            
            if rules._get_paid_amount(ps_order) and \
                    rules._get_paid_amount(ps_order) >= 0.0 :
                amount = float(rules._get_paid_amount(ps_order))
                order.openerp_id.automatic_payment(amount)
            
class sale_order_line(models.Model):
    _inherit = 'sale.order.line'
   
    prestashop_bind_ids = fields.One2many(
            comodel_name = 'prestashop.sale.order.line',
            inverse_name = 'openerp_id',
            string="PrestaShop Bindings"
        )
    prestashop_discount_bind_ids = fields.One2many(
            comodel_name = 'prestashop.sale.order.line.discount',
            inverse_name = 'openerp_id',
            string="PrestaShop Discount Bindings"
        )
    

class prestashop_sale_order_line(models.Model):
    _name = 'prestashop.sale.order.line'
    _inherit = 'prestashop.binding'
    _inherits = {'sale.order.line': 'openerp_id'}

    openerp_id = fields.Many2one(
            comodel_name = 'sale.order.line',
            string='Sale Order line',
            required=True,
            ondelete='cascade'
        )
    prestashop_order_id = fields.Many2one(
            comodel_name = 'prestashop.sale.order',
            string = 'Prestashop Sale Order',
            required=True,
            ondelete='cascade',
            select=True
        )
    

    @api.v7
    def create(self, cr, uid, vals, context=None):      
        prestashop_order_id = vals['prestashop_order_id']
        info = self.pool['prestashop.sale.order'].read(
            cr, uid,
            [prestashop_order_id],
            ['openerp_id'],
            context=context
        )
        order_id = info[0]['openerp_id']
        vals['order_id'] = order_id[0]
        return super(prestashop_sale_order_line, self).create(
            cr, uid, vals, context=context
        )


class prestashop_sale_order_line_discount(models.Model):
    _name = 'prestashop.sale.order.line.discount'
    _inherit = 'prestashop.binding'
    _inherits = {'sale.order.line': 'openerp_id'}

    openerp_id = fields.Many2one(
            comodel_name = 'sale.order.line',
            string='Sale Order line',
            required=True,
            ondelete='cascade'
        )
    prestashop_order_id = fields.Many2one(
            comodel_name = 'prestashop.sale.order',
            string = 'Prestashop Sale Order',
            required=True,
            ondelete='cascade',
            select=True
        )
    
    @api.v7
    def create(self, cr, uid, vals, context=None):
        prestashop_order_id = vals['prestashop_order_id']
        info = self.pool['prestashop.sale.order'].read(
            cr, uid,
            [prestashop_order_id],
            ['openerp_id'],
            context=context
        )
        order_id = info[0]['openerp_id']        
        vals['order_id'] = order_id[0]
        return super(prestashop_sale_order_line_discount, self).create(
            cr, uid, vals, context=context
        )

class prestashop_payment_method(models.Model):
    _inherit = 'payment.method'


    allow_zero=fields.Boolean("Allow to import Zero values")
    

# BACKEND

@prestashop
class PrestaShopSaleOrderOnChange(SaleOrderOnChange):
    _model_name = 'prestashop.sale.order'


@prestashop
class SaleOrderStateAdapter(GenericAdapter):
    _model_name = 'prestashop.sale.order.state'
    _prestashop_model = 'order_states'


@prestashop
class SaleOrderAdapter(GenericAdapter):
    _model_name = 'prestashop.sale.order'
    _prestashop_model = 'orders'
    _export_node_name = 'order'

    def update_sale_state(self, prestashop_id, datas):
        api = self.connect()        
        #order_histories = self.backend_record.get_version_ps_key('order_histories')
        resource =  self.backend_record.get_version_ps_key('order_histories')
        return api.add(resource, datas)

    def search(self, filters=None):
        result = super(SaleOrderAdapter, self).search(filters=filters)

        shop_ids = self.session.search('prestashop.shop', [
            ('backend_id', '=', self.backend_record.id)
        ])
        shops = self.session.browse('prestashop.shop', shop_ids)
        for shop in shops:
            if not shop.default_url:
                continue

            api = PrestaShopWebServiceDict(
                '%s/api' % shop.default_url, self.prestashop.webservice_key,
                client_args={'disable_ssl_certificate_validation': self.prestashop.trust_certificate}
            )
            result += api.search(self._prestashop_model, filters)
        return result    

@prestashop
class OrderCarriers(GenericAdapter):
    _model_name = '__not_exit_prestashop.order_carrier'
    _prestashop_model = 'order_carriers'
    _export_node_name = 'order_carrier'
 

@prestashop
class PaymentMethodAdapter(GenericAdapter):
    _model_name = 'payment.method'
    _prestashop_model = 'orders'
    _export_node_name = 'order'
    
    def search(self, filters=None):
        api = self.connect()
        res = api.get(self._prestashop_model, options=filters)
        methods = res[self._prestashop_model][self._export_node_name]
        if isinstance(methods, dict):
            return [methods]
        return methods

@prestashop
class SaleOrderLineAdapter(GenericAdapter):
    _model_name = 'prestashop.sale.order.line'
    _prestashop_model = 'order_details'


@prestashop
class SaleStateExport(ExportSynchronizer):
    _model_name = ['prestashop.sale.order']

    def run(self, prestashop_id, state):
        datas = {
            'order_history': {
                'id_order': prestashop_id,
                'id_order_state': state,
            }
        }
        self.backend_adapter.update_sale_state(prestashop_id, datas)


# TODO improve me, make the search on the sale order backend only
@on_record_write(model_names='sale.order')
def prestashop_sale_state_modified(session, model_name, record_id,
                                   fields=None):
    _logger.debug("Sale Order updated")
    if 'state' in fields:
        sale = session.browse(model_name, record_id)
        # a quick test to see if it is worth trying to export sale state        
        if len(sale.prestashop_bind_ids) == 1:            
            states = session.search(
                'sale.order.state.list',
                [('name', '=', sale.state)]
            )                                        
            if states:
                _logger.debug("State to search : %s and found ", (sale.state, ) )
                export_sale_state.delay(session, record_id, priority=20)
    return True


def find_prestashop_state(session, sale_state, backend_id):
    state_list_model = 'sale.order.state.list'
    state_list_ids = session.search(
        state_list_model,
        [('name', '=', sale_state)]
    )
    for state_list in session.browse(state_list_model, state_list_ids):
        if state_list.prestashop_state_id.backend_id.id == backend_id:
            return state_list.prestashop_state_id.prestashop_id
    return None


@job
def export_sale_state(session, record_id):
    inherit_model = 'prestashop.sale.order'
    sale_ids = session.search(inherit_model, [('openerp_id', '=', record_id)])
    if not isinstance(sale_ids, list):
        sale_ids = [sale_ids]
    for sale in session.browse(inherit_model, sale_ids):
        backend_id = sale.backend_id.id
        new_state = find_prestashop_state(session, sale.state, backend_id)
        if new_state is None:
            continue
        env = get_environment(session, inherit_model, backend_id)
        sale_exporter = env.get_connector_unit(SaleStateExport)
        sale_exporter.run(sale.prestashop_id, new_state)
