# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)


from ...unit.auto_matching_importer import AutoMatchingImporter
from openerp.addons.connector.unit.mapper import only_create, mapping
from ...backend import prestashop


@prestashop
class AccountTaxImporter(AutoMatchingImporter):
    _model_name = 'prestashop.account.tax'
    _erp_field = 'amount'
    _ps_field = 'rate'

    def _compare_function(self, ps_val, erp_val, ps_dict, erp_dict):
        if self.backend_record.taxes_included and erp_dict['price_include']:
            taxes_inclusion_test = True
        else:
            taxes_inclusion_test = not erp_dict['price_include']
        if not taxes_inclusion_test:
            return False
        return (erp_dict['type_tax_use'] == 'sale' and
                erp_dict['amount_type'] == 'percent' and
                abs(erp_val - float(ps_val)) < 0.01 and
                self.backend_record.company_id.id == erp_dict['company_id'][0])


    @only_create
    @mapping
    def openerp_id(self, record):
        """ Will bind the tax to an existing one with the same name and conf """
        tax = self.env['account.tax'].search([
                        ('name', '=', self.name(record)['name']),
                        ('company_id', '=', self.company_id(record)['company_id']),
                        ('amount', '=', self.amount(record)['amount']),
                        ('price_include', '=', self.price_include(record)['price_include']),
        ]   
        , limit=1)
        if tax:
            return {'openerp_id': tax.id}
