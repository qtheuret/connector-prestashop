from odoo.addons.component.core import AbstractComponent

import logging

_logger = logging.getLogger(__name__)

try:
    from prestapyt import PrestaShopWebServiceDict, PrestaShopWebServiceError
except:
    _logger.debug('Cannot import from `prestapyt`')


class GenericAdapter(AbstractComponent):
    _inherit = 'prestashop.adapter'

    def schema(self, attributes=None):
        """ Returns the schema of a model

        :rtype: dict
        """
        if not attributes:
            attributes = {}

        # Add schema=synopsis to attributes
        attributes['schema'] = 'synopsis'

        _logger.debug(
            'method synopsis, model %s, attributes %s',
            self._prestashop_model, unicode(attributes))
        return self.client.get(self._prestashop_model, options=attributes)
