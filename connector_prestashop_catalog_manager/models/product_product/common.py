# -*- coding: utf-8 -*-
# © 2016 Sergio Teruel <sergio.teruel@tecnativa.com>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import models, fields
from odoo.addons.queue_job.job import job


class ProductProduct(models.Model):
    _inherit = 'product.product'

    prestashop_bind_ids = fields.One2many(
        comodel_name='prestashop.product.combination',
        inverse_name='odoo_id',
        string='Prestashop Bindings',
    )
    no_export = fields.Boolean(
        string='No export to Prestashop',
    )

    def get_main_template_id(self, backend_id):
        self.ensure_one()

        if not self.product_tmpl_id:
            return False

        ps_templates = self.env['prestashop.product.template'].search([
            ('odoo_id', '=', self.product_tmpl_id.id),
            ('backend_id', '=', backend_id),
        ])
        if ps_templates:
            return ps_templates[0].id
        else:
            return False

    def create_prestashop_bindings(self, backend_id):
        for record in self:
            if record.product_tmpl_id:
                record.product_tmpl_id.create_prestashop_bindings(backend_id)
            if not record.prestashop_bind_ids.filtered(lambda s: s.backend_id.id == backend_id):
                self.env['prestashop.product.combination'].create({
                    'backend_id': backend_id,
                    'odoo_id': record.id,
                    'main_template_id': record.get_main_template_id(backend_id),
                })


class PrestashopProductCombination(models.Model):
    _inherit = 'prestashop.product.combination'

    @job(default_channel='root.prestashop')
    def export_products(self, backend):
        """ Export products combination and products in Prestashop. """
        with backend.work_on('prestashop.product.combination') as work:
            exporter = work.component(usage='prestashop.product.combination.exporter')
            return exporter.run(self, fields)
