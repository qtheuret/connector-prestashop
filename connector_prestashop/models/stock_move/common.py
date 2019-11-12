# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.addons.component.core import Component


class StockLocation(models.Model):
    _inherit = 'stock.location'

    prestashop_synchronized = fields.Boolean(
        string='Sync with PrestaShop',
        help='Check this option to synchronize this location with PrestaShop')

    @api.model
    def get_prestashop_stock_locations(self):
        prestashop_locations = self.search([
            ('prestashop_synchronized', '=', True),
            ('usage', '=', 'internal'),
        ])
        return prestashop_locations


class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.model
    def create(self, vals):
        location_obj = self.env['stock.location']
        ps_locations = location_obj.get_prestashop_stock_locations()
        move = super(StockMove, self).create(vals)
        if move.location_id in ps_locations or move.location_dest_id in ps_locations:
            move.product_id.update_prestashop_qty()
        return move

    @api.multi
    def write(self, vals):
        location_obj = self.env['stock.location']
        ps_locations = [l.id for l in location_obj.get_prestashop_stock_locations()]
        for move in self:
            src_location = vals.get('location_id', move.location_id.id)
            dest_location = vals.get('location_dest_id', move.location_dest_id.id)
            super(StockMove, self).write(vals)
            if src_location in ps_locations:
                move.invalidate_cache()
                move.product_id.update_prestashop_qty()
            if dest_location in ps_locations:
                move.invalidate_cache()
                move.product_id.update_prestashop_qty()
        return True

    @api.multi
    def unlink(self):
        ps_locations = self.env['stock.location'].\
            get_prestashop_stock_locations()
        self.filtered(lambda x: x.location_id in ps_locations).mapped(
            'product_id').update_prestashop_qty()
        self.filtered(lambda x: x.location_dest_id in ps_locations).mapped(
            'product_id').update_prestashop_qty()
        return super(StockMove, self).unlink()

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def create(self, vals):
        location_obj = self.env['stock.location']
        ps_locations = location_obj.get_prestashop_stock_locations()
        quant = super(StockQuant, self).create(vals)
        if quant.location_id in ps_locations:
            quant.product_id.update_prestashop_qty()
        return quant

    @api.multi
    def write(self, vals):
        location_obj = self.env['stock.location']
        ps_locations = [l.id for l in location_obj.get_prestashop_stock_locations()]
        for quant in self:
            location = vals.get('location_id', quant.location_id.id)
            super(StockQuant, self).write(vals)
            if location in ps_locations:
                quant.invalidate_cache()
                quant.product_id.update_prestashop_qty()
        return True

    @api.multi
    def unlink(self):
        ps_locations = self.env['stock.location'].\
            get_prestashop_stock_locations()
        self.filtered(lambda x: x.location_id in ps_locations).mapped(
            'product_id').update_prestashop_qty()
        return super(StockQuant, self).unlink()


class PrestashopStockPickingListener(Component):
    _name = 'prestashop.stock.picking.listener'
    _inherit = 'base.event.listener'
    _apply_on = ['stock.picking']

    def on_tracking_number_added(self, record):
        for binding in record.sale_id.prestashop_bind_ids:
            binding.with_delay().export_tracking_number()
