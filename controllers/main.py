# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint

from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class BlackstoneController(http.Controller):
    _process_url = '/payment/blackstone/process'
    _token_3ds_url = '/payment/blackstone/get_3ds_token'

    @http.route(_token_3ds_url, type='jsonrpc', auth='public', methods=['POST'], csrf=False)
    def blackstone_get_3ds_token(self, **post):
        """ Get 3DS credentials for the transaction. """
        reference = post.get('reference')
        if not reference:
            return {'error': "Missing transaction reference"}

        tx = request.env['payment.transaction'].sudo().search([('reference', '=', reference)], limit=1)
        if not tx:
             return {'error': "Transaction not found"}
        
        return tx.provider_id._blackstone_get_token_3ds()

    @http.route(_process_url, type='jsonrpc', auth='public', methods=['POST'], csrf=False)
    def blackstone_process_transaction(self, **post):
        """ Process the transaction for the Blackstone provider.

        :param dict post: The parameters received from the client.
        :return: None
        """
        _logger.info("Blackstone: processing transaction with data:\n%s", pprint.pformat(post))
        
        # Get the transaction reference
        tx_id = post.get('reference')
        if not tx_id:
             # Fallback if reference is not passed directly but as different key
             # Often JS passes 'reference' or 'processing_value'
             pass
        
        # We need to find the transaction based on the reference or id
        # Standard Odoo payment flow usually relies on the `payment.transaction` being created 
        # before this step, and we just need to update it with sensitive data.
        
        # In this implementation, we expect the JS to pass the transaction ID (int) or Reference (char)
        # For security, standard Odoo uses the `access_token` or similar but for this quick impl:
        
        # Let's assume the standard JS flow `_processProcessing` sends us the data.
        # Actually, standard Odoo 16+ `payment_form.js` `_onClickPay` triggers `_submitForm`
        # which calls `_processDirectPayment` if it's a direct payment.
        
        # We will assume we are receiving:
        # - reference: The transaction reference
        # - card_number
        # - exp_month
        # - exp_year
        # - cvc
        
        reference = post.get('reference')
        if not reference:
            return {'error': "Missing transaction reference"}

        tx = request.env['payment.transaction'].sudo().search([('reference', '=', reference)], limit=1)
        if not tx:
             return {'error': "Transaction not found"}

        # Update the transaction with card data (TEMPORARY - in memory only)
        # Since fields are store=False, we assign directly to the record cache
        tx.card_number = post.get('card_number')
        tx.exp_month = post.get('exp_month')
        tx.exp_year = post.get('exp_year')
        tx.cvc = post.get('cvc')
        
        # 3DS Data
        tx.secure_data = post.get('secure_data')
        tx.secure_transaction_id = post.get('secure_transaction_id')
        
        # --- Surcharge Logic ---
        # Add Surcharge/Card Difference as a line item to the Sales Order
        # This ensures accounting consistency.
        if tx.sale_order_ids:
            provider = tx.provider_id
            surcharge_product = request.env.ref('blackstone_payment.product_product_surcharge', raise_if_not_found=False)
            if not surcharge_product:
                surcharge_product = request.env['product.product'].sudo().search([('default_code', '=', 'SURCHARGE')], limit=1)
            
            if surcharge_product:
                total_surcharge = 0.0
                # Calculate base on the current transaction amount (assuming it doesn't include surcharge yet)
                # If we are retrying, we might need to be careful, but we check for existing line below.
                
                if provider.blackstone_surcharge_enabled:
                     total_surcharge += tx.amount * (provider.blackstone_surcharge_percent / 100)
                if provider.blackstone_card_difference_enabled:
                     total_surcharge += tx.amount * (provider.blackstone_card_difference_percent / 100)
                
                total_surcharge = round(total_surcharge, 2)

                if total_surcharge > 0:
                    for so in tx.sale_order_ids:
                        # Check if surcharge line already exists to avoid duplication
                        if not so.order_line.filtered(lambda l: l.product_id == surcharge_product):
                            _logger.info("Blackstone: Adding Surcharge line of %s to Order %s", total_surcharge, so.name)
                            # Add line
                            so.with_context(check_move_validity=False).write({'order_line': [
                                (0, 0, {
                                    'product_id': surcharge_product.id,
                                    'name': _("Card Fees / Surcharges"),
                                    'price_unit': total_surcharge,
                                    'product_uom_qty': 1.0,
                                    'tax_ids': [(5, 0, 0)], # Explicitly remove taxes
                                })
                            ]})
                            # Update Transaction Amount to reflect the new total
                            tx.amount += total_surcharge

        # Now trigger the payment request
        tx._send_payment_request()
        
        # After processing, we check the state
        # The `_send_payment_request` should handle the API call and update the state.
        
        return {
            'result': True,
            'reference': reference,
            'state': tx.state
        }
