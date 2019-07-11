# -*- coding: utf-8 -*-
# Copyright 2011-2013 Camptocamp
# Copyright 2011-2013 Akretion
# Copyright 2015 AvanzOSC
# Copyright 2015-2016 Tecnativa
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Prestashop-Odoo Catalog Manager",
    "version": "10.0.1.0.1",
    "license": "AGPL-3",
    "depends": [
        "connector_prestashop"
    ],
    "author": "Akretion,"
              "AvanzOSC,"
              "Tecnativa,"
              'Camptocamp SA,'
              "Odoo Community Association (OCA),"
              "Kerpeo",
    "website": "https://github.com/OCA/connector-prestashop",
    "category": "Connector",
    "data": [
        "views/prestashop_backend_view.xml",
        "views/prestashop_field_binding_view.xml",
        'views/product_attribute_view.xml',
        'views/product_view.xml',
    ],
    'installable': True,
}
