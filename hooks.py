# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import logging
from odoo import api, SUPERUSER_ID, tools

_logger = logging.getLogger(__name__)

def post_init_hook(env):
    """ Sets the default image for the Blackstone provider and ensures Journal configuration """
    provider = env['payment.provider'].search([('code', '=', 'blackstone')], limit=1)
    if provider:
        # 1. Set Image
        try:
            with tools.file_open('blackstone_payment/static/description/icon.png', 'rb') as f:
                icon_content = f.read()
                provider.write({'image_128': base64.b64encode(icon_content)})
            _logger.info("Blackstone provider icon set successfully.")
        except Exception as e:
            _logger.warning(f"Could not set Blackstone provider icon: {e}")

        # 2. Fix Journal Configuration (Validation Error fix)
        # Ensure the provider's journal has the 'Card' payment method in inbound lines
        if provider.journal_id:
            try:
                card_method = env.ref('payment.payment_method_card', raise_if_not_found=False)
                if card_method:
                    current_methods = provider.journal_id.inbound_payment_method_line_ids.mapped('payment_method_id')
                    if card_method not in current_methods:
                        _logger.info("Blackstone: Adding 'Card' payment method to journal %s", provider.journal_id.name)
                        provider.journal_id.write({
                            'inbound_payment_method_line_ids': [
                                (0, 0, {'payment_method_id': card_method.id, 'name': 'Card'})
                            ]
                        })
            except Exception as e:
                 _logger.error(f"Blackstone: Could not update journal configuration: {e}")

