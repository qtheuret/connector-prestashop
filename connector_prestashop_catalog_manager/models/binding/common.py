# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo import models, api


class PrestashopBinding(models.AbstractModel):
    _inherit = 'prestashop.binding'

    @api.multi
    def resync_export(self):
        for record in self:
            if self.env.context.get('connector_delay'):
                # Always run export with en_US lang
                record.witch_context({'lang': 'en_US'}).with_delay().export_record()
            for record in self:
                record.with_context({'lang': 'en_US'}).export_record()

        return True

    @api.model
    def get_schema(self, backend, force=False):
        """ Import a record from PrestaShop """
        self.check_active(backend)
        with backend.work_on(self._name) as work:
            importer = work.component(usage='record.importer')
            res = importer.get_schema(force=force)
            return self.import_schema(backend_record=backend, schema=res)

    @api.model
    def import_schema(self, backend_record=None, schema=None):
        """
        Create fields.binding records for each field in schema
        :param schema:
        :return:
        """
        if not schema:
            return True

        fld_bind = self.env['prestashop.field.binding']

        for model, fields in schema.items():
            for fld in fields:
                # Get existing field binding
                fld_domain = [
                    ('backend_id', '=', backend_record.id),
                    ('odoo_model', '=', self._name),
                    ('prestashop_model', '=', model),
                    ('prestashop_field', '=', fld),
                ]
                if not fld_bind.search(fld_domain):
                    fld_bind.create({
                        'backend_id': backend_record.id,
                        'odoo_model': self._name,
                        'prestashop_model': model,
                        'prestashop_field': fld,
                    })
