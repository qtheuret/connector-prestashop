# -*- coding: utf-8 -*-
##############################################################################
#
#    Prestashoperpconnect : OpenERP-PrestaShop connector
#    Copyright 2013 Camptocamp SA
#    Copyright (C) 2013 Akretion (http://www.akretion.com/)
#    Copyright (C) 2015 Tech-Receptives(<http://www.tech-receptives.com>)
#    @author: Guewen Baconnier
#    @author: Alexis de Lattre <alexis.delattre@akretion.com>
#    @author Sébastien BEAU <sebastien.beau@akretion.com>
#    @author Arthur Vuillard
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


import base64
import logging
from prestapyt import PrestaShopWebServiceError, PrestaShopWebServiceDict, PrestaShopWebService
from openerp.addons.connector.unit.backend_adapter import CRUDAdapter
from ..backend import prestashop


_logger = logging.getLogger(__name__)
# TODO : Fix this part https://github.com/pedrobaeza/connector-prestashop/commit/3226992f1ee3a3c74f388c65d174c96bcd5e14e7#commitcomment-13580782
#handler = logging.FileHandler('/opt/odoo/v8/adapter_log.log')
#handler = logging.FileHandler('adapter_log.log')
#handler.setLevel(logging.INFO)
#formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#handler.setFormatter(formatter)
#_logger.addHandler(handler)


    
class MyPrestaShopWebServiceDict(PrestaShopWebServiceDict):
    
    def _validate_query_options(self, options):
        """
        Check options against supported options
        (reference : http://doc.prestashop.com/display/PS14/Cheat-sheet+-+Concepts+outlined+in+this+tutorial)
        @param options: dict of options to use for the request
        @return: True if valid, else raise an error PrestaShopWebServiceError
        """
        _logger.debug("======= Validate Options M&GO %s" % options)
        if not isinstance(options, dict):
            raise PrestaShopWebServiceError('Parameters must be a instance of dict')
        supported = ('filter', 'display', 'sort', 'limit', 'schema', 'date', 'id_shop', 'price')
        # filter[firstname] (as e.g.) is allowed, so check only the part before a [
        unsupported = set([param.split('[')[0] for param in options]).difference(supported)
        if unsupported:
            raise PrestaShopWebServiceError('Unsupported parameters: %s'
            % (', '.join(tuple(unsupported)),))
        return True



    
    
class PrestaShopWebServiceImage(PrestaShopWebServiceDict):

    def get_image(self, resource, resource_id=None, image_id=None,
                  options=None):
        full_url = self._api_url + 'images/' + resource
        if resource_id is not None:
            full_url += "/%s" % (resource_id,)
            if image_id is not None:
                full_url += "/%s" % (image_id)
        if options is not None:
            self._validate_query_options(options)
            full_url += "?%s" % (self._options_to_querystring(options),)
        response = self._execute(full_url, 'GET')
        if response:
            #INFO : This syntax is used when prestapyt 0.4 from akretion is used
#            image_content = base64.b64encode(response.content)
            #INFO : This syntax is used when prestapyt 0.6.2 is used
            image_content = base64.b64encode(response[2])
        else:
            image_content = ''
            
        
        return {
            #INFO : This syntax is used when prestapyt 0.4 from akretion is used
#            'type': response.headers['content-type'],
            #INFO : This syntax is used when prestapyt 0.6.2 is used
            'type': response[1].get('content-type'),
            'content': image_content,
            'id_' + resource[:-1]: resource_id,
            'id_image': image_id
        }



class PrestaShopLocation(object):

    def __init__(self, location, webservice_key, api_debug, api_timeout, trust_certificate):
        self.location = location
        self.webservice_key = webservice_key
        self.api_url = '%s/api' % location
        self.api_debug = api_debug
        self.api_timeout = api_timeout
        self.trust_certificate = trust_certificate


class PrestaShopCRUDAdapter(CRUDAdapter):

    """ External Records Adapter for PrestaShop """

    def __init__(self, environment):
        """

        :param environment: current environment (backend, session, ...)
        :type environment: :py:class:`connector.connector.Environment`
        """
        super(PrestaShopCRUDAdapter, self).__init__(environment)
        self.prestashop = PrestaShopLocation(
            self.backend_record.location,
            self.backend_record.webservice_key,
            self.backend_record.api_debug,
            self.backend_record.api_timeout,
            self.backend_record.trust_certificate
        )

    def search(self, filters=None):
        """ Search records according to some criterias
        and returns a list of ids """
        raise NotImplementedError

    def read(self, id, attributes=None):
        """ Returns the information of a record """
        raise NotImplementedError

    def search_read(self, filters=None):
        """ Search records according to some criterias
        and returns their information"""
        raise NotImplementedError

    def create(self, data):
        """ Create a record on the external system """
        raise NotImplementedError

    def write(self, id, data):
        """ Update records on the external system """
        raise NotImplementedError

    def delete(self, id):
        """ Delete a record on the external system """
        raise NotImplementedError


class GenericAdapter(PrestaShopCRUDAdapter):

    _model_name = None
    _prestashop_model = None

    def connect(self):
        # Add parameter to debug 
        # https://github.com/akretion/prestapyt/blob/master/prestapyt/prestapyt.py#L81
        _logger.info("Connect to %s with apikey %s in debug mode %s and " + 
                        "timeout %s",
                        self.prestashop.api_url,
                        self.prestashop.webservice_key,
                        str(self.prestashop.api_debug),
                        str(self.prestashop.api_timeout)
                        )
        return MyPrestaShopWebServiceDict(self.prestashop.api_url,
                                        self.prestashop.webservice_key,
                                        self.prestashop.api_debug, 
#                                        None,
#                                        {'timeout': self.prestashop.api_timeout}
                                        client_args={'disable_ssl_certificate_validation': self.prestashop.trust_certificate}
                                        )

    def search(self, filters=None):
        """ Search records according to some criterias
        and returns a list of ids

        :rtype: list
        """
        _logger.info('method search, model %s, filters %s', self._prestashop_model, unicode(filters))
        api = self.connect()
        return api.search(self._prestashop_model, filters)

    def read(self, id, attributes=None):
        """ Returns the information of a record

        :rtype: dict
        """
        _logger.info('method read, model %s id %s, attributes %s', self._prestashop_model, str(id),unicode(attributes))
        # TODO rename attributes in something better
        api = self.connect()
        res = api.get(self._prestashop_model, id, options=attributes)
        first_key = res.keys()[0]
        return res[first_key]

    def create(self, attributes=None):
        """ Create a record on the external system """
        _logger.info('method create, model %s, attributes %s', self._prestashop_model, unicode(attributes))
         
        api = self.connect()
        return api.add(self._prestashop_model, {
            self._export_node_name: attributes
        })

    def write(self, id, attributes=None):
        """ Update records on the external system """
        api = self.connect()
        attributes['id'] = id
        _logger.info('method write, model %s, attributes %s', self._prestashop_model, unicode(attributes))
         
        return api.edit(self._prestashop_model, id, {
            self._export_node_name: attributes
        })

    def delete(self, ids):
        """ Delete a record(s) on the external system """
        _logger.info('method delete, model %s, ids %s', self._prestashop_model, unicode(ids))
         
        api = self.connect()
        return api.delete(self._prestashop_model, ids)


@prestashop
class ShopGroupAdapter(GenericAdapter):
    _model_name = 'prestashop.shop.group'
    _prestashop_model = 'shop_groups'


@prestashop
class ShopAdapter(GenericAdapter):
    _model_name = 'prestashop.shop'
    _prestashop_model = 'shops'


@prestashop
class ResLangAdapter(GenericAdapter):
    _model_name = 'prestashop.res.lang'
    _prestashop_model = 'languages'


@prestashop
class ResCountryAdapter(GenericAdapter):
    _model_name = 'prestashop.res.country'
    _prestashop_model = 'countries'


@prestashop
class ResCurrencyAdapter(GenericAdapter):
    _model_name = 'prestashop.res.currency'
    _prestashop_model = 'currencies'


@prestashop
class PConfigurationAdapter(GenericAdapter):
    _model_name = 'prestashop.configuration'
    _prestashop_model = 'configurations'


@prestashop
class AccountTaxAdapter(GenericAdapter):
    _model_name = 'prestashop.account.tax'
    _prestashop_model = 'taxes'


@prestashop
class TaxRuleAdapter(GenericAdapter):
    _model_name = 'prestashop.tax.rule'
    _prestashop_model = 'tax_rules'


#@prestashop
#class PartnerCategoryAdapter(GenericAdapter):
#    _model_name = 'prestashop.res.partner.category'
#    _prestashop_model = 'groups'


@prestashop
class PartnerAdapter(GenericAdapter):
    _model_name = 'prestashop.res.partner'
    _prestashop_model = 'customers'


@prestashop
class PartnerAddressAdapter(GenericAdapter):
    _model_name = 'prestashop.address'
    _prestashop_model = 'addresses'



@prestashop
class SupplierImageAdapter(PrestaShopCRUDAdapter):
    _model_name = 'prestashop.supplier.image'
    _prestashop_image_model = 'suppliers'

    def read(self, supplier_id, options=None):
        api = PrestaShopWebServiceImage(self.prestashop.api_url,
                                        self.prestashop.webservice_key,
                                        client_args={'disable_ssl_certificate_validation': self.prestashop.trust_certificate})
        res = api.get_image(
            self._prestashop_image_model,
            supplier_id,
            options=options
        )
        return res['content']


@prestashop
class TaxGroupAdapter(GenericAdapter):
    _model_name = 'prestashop.account.tax.group'
    _prestashop_model = 'tax_rule_groups'


@prestashop
class OrderPaymentAdapter(GenericAdapter):
    _model_name = '__not_exist_prestashop.payment'
    _prestashop_model = 'order_payments'


@prestashop
class OrderDiscountAdapter(GenericAdapter):
    _model_name = 'prestashop.sale.order.line.discount'
    _prestashop_model = 'order_discounts'


@prestashop
class SupplierAdapter(GenericAdapter):
    _model_name = 'prestashop.supplier'
    _prestashop_model = 'suppliers'


@prestashop
class SupplierInfoAdapter(GenericAdapter):
    _model_name = 'prestashop.product.supplierinfo'
    _prestashop_model = 'product_suppliers'


@prestashop
class MailMessageAdapter(GenericAdapter):
    _model_name = 'prestashop.mail.message'
    _prestashop_model = 'messages'


@prestashop
class PricelistAdapter(GenericAdapter):
    _model_name = 'prestashop.groups.pricelist'
    _prestashop_model = 'groups'

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
