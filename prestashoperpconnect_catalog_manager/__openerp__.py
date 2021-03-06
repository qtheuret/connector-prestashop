# -*- encoding: utf-8 -*-
###############################################################################
#
#   Prestashop_catalog_manager for OpenERP
#   Copyright (C) 2012-TODAY Akretion <http://www.akretion.com>.
#   All Rights Reserved
#   @author : Sébastien BEAU <sebastien.beau@akretion.com>
#             Benoît GUILLOT <benoit.guillot@akretion.com>
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

{
    "name": "Prestashop-OpenERP Catalog Manager",
    "version": "0.2",
    "license": "AGPL-3",
    "depends": [
        "prestashoperpconnect"
    ],
    "author": "PrestashopERPconnect Core Editors",
    "description": """This module is an extention for PrestashopERPconnect.

With this module you will be able to manage your catalog directly from OpenERP.
  You can :
- create/modify attributtes and values in Odoo and push then in
  pretashop.
- create/modify products and push then in prestashop.
- create/modify products variant and push the in prestashop (combinations).

TODO :
- create/modify category and push then in prestashop.
- create/modify image and push then in prestashop.
""",
    'images': [
    ],
    "website": "https://launchpad.net/prestashoperpconnect",
    "category": "Generic Modules",
    "complexity": "expert",
    "demo": [],
    "data": [
        'product_attribute_view.xml',
        'product_view.xml',
        'wizard/export_multiple_products_view.xml',
        'wizard/sync_products_view.xml'
    ],
    "active": False,
    "installable": False,
    "application": True,
}
