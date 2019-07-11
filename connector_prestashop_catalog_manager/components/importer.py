# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from contextlib import closing, contextmanager

import odoo
from odoo import _

from odoo.addons.queue_job.exception import (
    RetryableJobError,
    FailedJobError,
)

from odoo.addons.component.core import AbstractComponent

_logger = logging.getLogger(__name__)


class PrestashopImporter(AbstractComponent):
    """ Base importer for PrestaShop """

    _inherit = 'prestashop.importer'

    def get_schema(self, force=False):
        """ Return the raw prestashop data for ``self.prestashop_id`` """
        return self.backend_adapter.schema()