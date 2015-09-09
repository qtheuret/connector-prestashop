# -*- coding: utf-8 -*-
###############################################################################
#
#   Module for OpenERP
#   Copyright (C) 2014 Akretion (http://www.akretion.com).
#   @author Sébastien BEAU <sebastien.beau@akretion.com>
#   @author Guewen Baconnier
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################


from openerp.osv import fields, orm

from openerp.addons.connector.session import ConnectorSession

from openerp.addons.prestashoperpconnect.unit.import_synchronizer import import_record


class res_partner(orm.Model):
    _inherit = 'res.partner'

    _columns = {
        'prestashop_supplier_bind_ids': fields.one2many(
            'prestashop.supplier',
            'openerp_id',
            string="Prestashop supplier bindings",
        ),
    }


class prestashop_supplier(orm.Model):
    _name = 'prestashop.supplier'
    _inherit = 'prestashop.binding'
    _inherits = {'res.partner': 'openerp_id'}

    _columns = {
        'openerp_id': fields.many2one(
            'res.partner',
            string='Partner',
            required=True,
            ondelete='cascade'
        ),
    }


class product_supplierinfo(orm.Model):
    _inherit = 'product.supplierinfo'

    _columns = {
        'prestashop_bind_ids': fields.one2many(
            'prestashop.product.supplierinfo',
            'openerp_id',
            string="Prestashop bindings",
        ),
    }


class prestashop_product_supplierinfo(orm.Model):
    _name = 'prestashop.product.supplierinfo'
    _inherit = 'prestashop.binding'
    _inherits = {'product.supplierinfo': 'openerp_id'}

    _columns = {
        'openerp_id': fields.many2one(
            'product.supplierinfo',
            string='Supplier info',
            required=True,
            ondelete='cascade'
        ),
    }
