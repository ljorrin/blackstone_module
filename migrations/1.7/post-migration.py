# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

_logger = logging.getLogger(__name__)

def migrate(cr, version):
    """
    Fix the Blackstone Payment Journal configuration.
    Ensures that the 'Card' payment method is assigned to the journal's inbound payment method lines.
    This resolves the ValidationError: "Please define a payment method line on your payment."
    """
    from odoo import api, SUPERUSER_ID
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # 1. Find the Blackstone provider
    provider = env['payment.provider'].search([('code', '=', 'blackstone')], limit=1)
    if not provider:
        _logger.warning("Blackstone: Migration skipped, provider not found.")
        return

    # 2. Find or Create the 'blackstone' account.payment.method
    account_payment_method = env['account.payment.method'].search([
        ('code', '=', 'blackstone'),
        ('payment_type', '=', 'inbound')
    ], limit=1)
    
    if not account_payment_method:
        _logger.info("Blackstone: Creating account.payment.method for 'blackstone'")
        account_payment_method = env['account.payment.method'].sudo().create({
            'name': 'Blackstone',
            'code': 'blackstone',
            'payment_type': 'inbound',
        })

    # 3. Check and update the journal
    # Usually we want to use a Bank journal for online payments
    journal = provider.journal_id
    if not journal:
        journal = env['account.journal'].search([('type', '=', 'bank'), ('company_id', '=', provider.company_id.id)], limit=1)
        if journal:
            _logger.info("Blackstone: Assigning journal %s to provider.", journal.name)
            provider.journal_id = journal

    if journal:
        # Look for a line that is specifically for THIS provider
        current_line = journal.inbound_payment_method_line_ids.filtered(lambda l: l.payment_provider_id == provider)
        
        if not current_line:
            _logger.info("Blackstone: Adding payment method line for provider %s to journal %s", provider.name, journal.name)
            journal.write({
                'inbound_payment_method_line_ids': [
                    (0, 0, {
                        'payment_method_id': account_payment_method.id, 
                        'name': provider.name,
                        'payment_provider_id': provider.id,
                    })
                ]
            })
        else:
            # Ensure it has the correct payment_method_id to avoid domain issues
            if current_line.payment_method_id != account_payment_method:
                _logger.info("Blackstone: Updating payment_method_id for existing line in journal %s", journal.name)
                current_line.write({'payment_method_id': account_payment_method.id})
            _logger.info("Blackstone: Journal %s already has a valid line for provider %s.", journal.name, provider.name)
    else:
        _logger.warning("Blackstone: No bank journal found to link the provider.")
