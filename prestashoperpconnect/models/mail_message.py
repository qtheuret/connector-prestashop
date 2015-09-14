# -*- coding: utf-8 -*-
##############################################################################
#
#    Prestashoperpconnect : OpenERP-PrestaShop connector
#    Copyright (C) 2013 Akretion (http://www.akretion.com/)
#    @author: Alexis de Lattre <alexis.delattre@akretion.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program. If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp.osv.orm import Model
from openerp.osv import fields


class MailMessage(Model):
    _inherit = 'mail.message'

    _columns = {
        'prestashop_bind_ids': fields.one2many(
            'prestashop.mail.message',
            'openerp_id',
            string="Prestashop Bindings"
        ),
    }


class PrestashopMailMessage(Model):
    _name = "prestashop.mail.message"
    _inherit = "prestashop.binding"
    _inherits = {'mail.message': 'openerp_id'}

    _columns = {
        'openerp_id': fields.many2one(
            'mail.message',
            string="Message",
            required=True,
            ondelete='cascade'
        ),
    }
