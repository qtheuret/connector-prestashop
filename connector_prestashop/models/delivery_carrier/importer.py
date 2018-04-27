# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import logging
from openerp.addons.connector.queue.job import job
from openerp.addons.connector.unit.mapper import (mapping,
                                                  ImportMapper,
                                                  only_create
                                                  )
from ...unit.importer import (
    DelayedBatchImporter,
    PrestashopImporter,
    import_batch,
)
from ...backend import prestashop

_logger = logging.getLogger(__name__)


@prestashop
class DeliveryCarrierImporter(PrestashopImporter):
    _model_name = ['prestashop.delivery.carrier']


@prestashop
class CarrierImportMapper(ImportMapper):
    _model_name = 'prestashop.delivery.carrier'
    direct = [
        ('name', 'name_ext'),
        ('name', 'name'),
    ]

    @mapping
    def id_reference(self, record):
        id_reference = int(str(record['id_reference']))
        return {'id_reference': id_reference}

    #TODO :
    # id_reference à mapper en only_create
    @only_create
    @mapping
    def openerp_id(self, record):
        #Prevent The duplication of delivery method if id_reference is the same 
        id_reference = record['id_reference']
        id_reference = int(str(record['id_reference']))
        ps_delivery = self.env['prestashop.delivery.carrier'].search([
            ('id_reference', '=', id_reference),
            ('backend_id', '=', self.backend_record.id)])
        _logger.debug("Found delivery %s for reference %s" % (ps_delivery, id_reference))
        if len(ps_delivery) == 1 :
            #Temporary defensive mode so that only a single delivery method still available
            delivery = ps_delivery.openerp_id
            ps_delivery.unlink()
            return {'openerp_id': delivery.id}
        else:
            return {}  
    
    
    
    @mapping
    def active(self, record):
        return {'active_ext': record['active'] == '1'}

    @mapping
    def product_id(self, record):
        if self.backend_record.shipping_product_id:
            return {'product_id': self.backend_record.shipping_product_id.id}
        prod_mod = self.session.pool['product.product']
        default_ship_product = prod_mod.search(
            self.session.cr,
            self.session.uid,
            [('default_code', '=', 'SHIP'),
             ('company_id', '=', self.backend_record.company_id.id)],
        )
        if default_ship_product:
            return {'product_id': default_ship_product[0]}
        return {}

    @mapping
    def partner_id(self, record):
        partner_pool = self.session.pool['res.partner']
        default_partner = partner_pool.search(
            self.session.cr,
            self.session.uid,
            [],
        )[0]
        return {'partner_id': default_partner}

    @mapping
    def prestashop_id(self, record):
        return {'prestashop_id': record['id']}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def company_id(self, record):
        return {'company_id': self.backend_record.company_id.id}


@prestashop
class DeliveryCarrierBatchImporter(DelayedBatchImporter):
    """ Import the PrestaShop Carriers.
    """
    _model_name = ['prestashop.delivery.carrier']

    def run(self, filters=None, **kwargs):
        """ Run the synchronization """
        record_ids = self.backend_adapter.search()
        _logger.info('search for prestashop carriers %s returned %s',
                     filters, record_ids)
        for record_id in record_ids:
            self._import_record(record_id, **kwargs)


@job(default_channel='root.prestashop')
def import_carriers(session, backend_id):
    import_batch(
        session, 'prestashop.delivery.carrier', backend_id, priority=5
    )
