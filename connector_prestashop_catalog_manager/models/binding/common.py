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