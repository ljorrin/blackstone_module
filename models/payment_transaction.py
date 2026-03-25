import logging
import pprint
import requests
import json

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

import hashlib
import uuid
import time
from odoo.http import request

class PaymentTransactionBlackstone(models.Model):
    _inherit = 'payment.transaction'

    # Using store=False avoids database column errors and improves security
    card_number = fields.Char(string='Card Number', store=False)
    exp_month = fields.Char(string='Expiration Month', store=False)
    exp_year = fields.Char(string='Expiration Year', store=False)
    cvc = fields.Char(string='CVC', store=False)
    secure_data = fields.Char(string='3DS Secure Data', store=False)
    secure_transaction_id = fields.Char(string='3DS Secure Transaction ID', store=False)

    def _get_specific_processing_values(self, processing_values):
        """ Return the specific processing values for the transaction. """
        res = super()._get_specific_processing_values(processing_values)
        if self.provider_code != 'blackstone':
            return res

        # Ensure reference is passed to frontend if not already available
        # The base `_get_processing_values` usually handles `reference`, but `specific` allows custom data.
        # We don't strictly need extra data for the form initiation if we read from the form inputs,
        # but returning at least the reference is good practice for the flow.
        return res



    def _send_payment_request(self):
        """Send payment request to Blackstone API."""
        self.ensure_one()
        provider = self.provider_id
        if provider.code != 'blackstone':
            return super(PaymentTransactionBlackstone, self)._send_payment_request()

        # Decide if New Card or Saved Card (Token)
        if self.token_id:
            # Saved Card Flow: Transactions/SaleWithToken
            endpoint = "Transactions/SaleWithToken"
            payload = {
                "Token": self.token_id.provider_ref,
                "UserName": provider.blackstone_api_username,
                "Password": provider.blackstone_api_password,
                "mid": provider.blackstone_api_mid,
                "cid": provider.blackstone_api_cid,
                "AppKey": provider.blackstone_app_key,
                "AppType": provider.blackstone_app_type,
                "Amount": self.amount,
                 # "SurchargeAmount": ..., "TaxAmount": ... (Optional based on need)
                "TransactionType": 2, # SaleWithToken
                "Reference": self.reference,
                "SecureData": self.secure_data or "",
                "SecureTransactionId": self.secure_transaction_id or "",
            }
        else:
            # New Card Flow: Transactions/Sale
            endpoint = "Transactions/Sale"
            
            # Basic validation of required card fields
            required_fields = {
                'card_number': self.card_number,
                'exp_month': self.exp_month,
                'exp_year': self.exp_year,
                'cvc': self.cvc,
            }
            missing = [name for name, value in required_fields.items() if not value]
            if missing:
                raise ValidationError(_(
                    "Missing required card fields: %s. Please try again." % ", ".join(missing)
                ))

            # Format Expiry (MMYY)
            # Ensure 2 digits
            mm = self.exp_month.zfill(2)
            yy = self.exp_year[-2:] if len(self.exp_year) >= 2 else self.exp_year.zfill(2)
            exp_date = f"{mm}{yy}"
            
            # Get IP
            partner_ip = request.httprequest.remote_addr if request else '127.0.0.1'
            
            # Generate Unique Transaction Number (replacement for PHP md5(uniqid(...)))
            unique_str = f"{self.reference}-{time.time()}-{uuid.uuid4()}"
            userTransactionNumber = hashlib.md5(unique_str.encode('utf-8')).hexdigest()

            # Get Merchant Settings for Surcharges (Use stored values from Provider)
            surcharge_amount = 0.0
            card_difference_amount = 0.0
            
            # Use `self.amount` (Total) to back-calculate Base Amount
            # We assume self.amount includes the surcharges because the Controller adds them to the Sale Order.
            # Total = Base * (1 + rates)
            total_rate = 0.0
            if provider.blackstone_surcharge_enabled:
                total_rate += provider.blackstone_surcharge_percent
            if provider.blackstone_card_difference_enabled:
                total_rate += provider.blackstone_card_difference_percent
                
            if total_rate > 0:
                # Calculate Base Amount from Total
                base_amount = round(self.amount / (1 + total_rate / 100), 2)
                
                # Re-calculate specific amounts based on the derived Base Amount
                if provider.blackstone_surcharge_enabled:
                    surcharge_amount = round(base_amount * (provider.blackstone_surcharge_percent / 100), 2)
                    _logger.info("Blackstone: Applies Surcharge: %s (Base: %s)", surcharge_amount, base_amount)
                    
                if provider.blackstone_card_difference_enabled:
                    card_difference_amount = round(base_amount * (provider.blackstone_card_difference_percent / 100), 2)
                    _logger.info("Blackstone: Applies Card Difference: %s (Base: %s)", card_difference_amount, base_amount)
                
                # If using 3DS Test MID, some combos of card difference might fail
                #if provider.blackstone_api_mid == '98208' and card_difference_amount > 0:
                #     _logger.warning("Blackstone: Sandbox MID 98208 typically doesn't support CardDifferenceAmount. Forcing 0 for testing.")
                #     card_difference_amount = 0.0
            else:
                base_amount = self.amount

            # Tip: Gateway expects "Amount" to be the Base Amount if it adds surcharges itself.
            # Based on user feedback: "Amount 12.24... plus 0.24... is not correct".
            # This implies we must send Base Amount in "Amount".

            payload = {
                "UserName": provider.blackstone_api_username,
                "Password": provider.blackstone_api_password,
                "mid": provider.blackstone_api_mid,
                "cid": provider.blackstone_api_cid,
                "AppKey": provider.blackstone_app_key,
                "AppType": provider.blackstone_app_type,
                "Amount": base_amount,
                "TaxAmount": 0,
                "TipAmount": 0,
                "SurchargeAmount": surcharge_amount,
                "CardDifferenceAmount": card_difference_amount,
                "TransactionType": 1, # Sale
                "ZipCode": self.partner_zip,
                "CardNumber": self.card_number.replace(' ', ''),
                "ExpDate": exp_date,
                "CVN": self.cvc,
                "NameOnCard": self.partner_name,
                "UserTransactionNumber": userTransactionNumber,
                "Source": "BPaydPluginOdoo",
                "SecureData": self.secure_data or "",
                "PosCode": "Moto",
                "SecureTransactionId": self.secure_transaction_id or "",
                "SaveToken": "True",
                "x_first_name": self.partner_id.name.split(" ")[0] if self.partner_id.name else "", # Simple split
                "x_last_name": " ".join(self.partner_id.name.split(" ")[1:]) if self.partner_id.name and len(self.partner_id.name.split(" ")) > 1 else "",
                "x_address": self.partner_address, 
                "x_city": self.partner_city,
                "x_state": self.partner_state_id.name if self.partner_state_id else "",
                "x_zip": self.partner_zip,
                "x_country": self.partner_country_id.name if self.partner_country_id else "",
                "x_phone": self.partner_phone,
                "x_email": self.partner_email,
                "SaveCustomer": "True",
                "IsTest": "True" if provider.state == 'test' or provider.blackstone_test_mode else "False",
                "CustomerId": self.partner_id.id,
                "CustomerPhone": self.partner_phone,
                "CustomerEmail": self.partner_email,
                "CustomerCountry": self.partner_country_id.name if self.partner_country_id else "",
                "CustomerState": self.partner_state_id.name if self.partner_state_id else "",
                "CustomerCity": self.partner_city,
                "CustomerAddress": self.partner_address,
                "OrderReference": self.reference, 
                "x_ship_to_first_name": self.partner_id.name.split(" ")[0] if self.partner_id.name else "",
                "x_ship_to_last_name": " ".join(self.partner_id.name.split(" ")[1:]) if self.partner_id.name and len(self.partner_id.name.split(" ")) > 1 else "",
                "x_ship_to_company": self.partner_id.parent_id.name if self.partner_id.parent_id else "",
                "x_ship_to_address": self.partner_address,
                "x_ship_to_city": self.partner_city,
                "x_ship_to_country": self.partner_country_id.name if self.partner_country_id else "",
                "x_ship_to_state": self.partner_state_id.name if self.partner_state_id else "",
                "x_ship_to_zip": self.partner_zip,
                "x_cust_id": self.partner_id.id,
                "x_customer_ip": partner_ip            
            }

        # Make Request
        # Note: _send_api_request is a nice helper if it exists in the provider customization, 
        # but since I haven't implemented it in payment_provider.py, I should use `requests` directly 
        # OR assume `_make_blackstone_request` helper. 
        # Since I am in `payment.transaction`, I should implement the request logic here or calls provider.
        
        # We will use simple requests here for clarity as provider helper helper is not confirmed.
        import requests
        import json
        
        url = f"{provider._blackstone_get_api_url()}/{endpoint}"
        headers = {'Content-Type': 'application/x-www-form-urlencoded'} # PHP uses this
        
        try:
            # PHP uses http_build_query, requests.post with `data` does form-urlencoded
            _logger.info("Blackstone Payment Request to %s: %s", url, pprint.pformat(payload))
            response = requests.post(url, data=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            _logger.info("Blackstone Payment Response: %s", pprint.pformat(data))
        except Exception as e:
            _logger.error("Blackstone Connection Error: %s", e)
            self._set_error(_("Could not connect to payment processor."))
            return

        # Handle Response
        # PHP: if (isset($resp['ResponseCode']) && $resp['ResponseCode'] == "200")
        if str(data.get('ResponseCode')) == '200':
            # Success
            self.provider_reference = data.get('ServiceReferenceNumber')
            self._set_done(state_message=_('Payment approved. Ref: %s') % data.get('ServiceReferenceNumber'))
            
            # Handle Token Creation
            if self.tokenize and not self.token_id:
                token_str = data.get('Token')
                if token_str:
                    self._blackstone_create_token(token_str, data)

        else:
            # Show the specific display message from the API
            error_msg = data.get('displayMessage') or data.get('Message') or _('Payment failed')
            self._set_error(error_msg)

        # Cleanup
        # Cleanup not needed for store=False fields as they are not persisted
        pass

    def _blackstone_create_token(self, token_str, data):
        """Create a payment.token for the saved card."""
        self.ensure_one()
        payment_token = self.env['payment.token'].create({
            'provider_id': self.provider_id.id,
            'payment_method_id': self.payment_method_id.id,
            'payment_details': f"{data.get('CardType', 'Card')} •••• {data.get('LastFour', '0000')}",
            'partner_id': self.partner_id.id,
            'provider_ref': token_str,
            # 'verified': True,
        })
        self.token_id = payment_token.id
        self.write({'token_id': payment_token.id})
    def _send_refund_request(self, amount_to_refund=None):
        """Send a refund request to Blackstone."""
        self.ensure_one()
        provider = self.provider_id
        
        # Determine amount
        refund_amount = amount_to_refund or self.amount
        
        # Endpoint
        endpoint = "Transactions/DoRefund"
        url = f"{provider._blackstone_get_api_url()}/{endpoint}"
        
        # Service Reference (Required)
        # For a refund transaction, we need the reference of the source transaction
        service_reference = self.source_transaction_id.provider_reference
        if not service_reference:
             raise ValidationError(_("Cannot refund transaction without a provider reference."))

        # Generate User Transaction Number (Unique)
        unique_str = f"{service_reference}-{url}-{time.time()}-{uuid.uuid4()}"
        user_txn_number = hashlib.md5(unique_str.encode('utf-8')).hexdigest()

        # Get IP
        partner_ip = request.httprequest.remote_addr if request else '127.0.0.1'

        payload = {
            "Amount": refund_amount * -1,
            "TrackData": "",
            "UserTransactionNumber": user_txn_number,
            "ServiceTransactionNumber": service_reference,
            "SURI": "",
            "AppKey": provider.blackstone_app_key,
            "AppType": provider.blackstone_app_type,
            "mid": provider.blackstone_api_mid,
            "cid": provider.blackstone_api_cid,
            "UserName": provider.blackstone_api_username,
            "Password": provider.blackstone_api_password,
            "IpAddress": partner_ip,
            "IsTest": "True" if provider.blackstone_test_mode else "False",
        }

        try:
             _logger.info("Blackstone Refund Request to %s: %s", url, pprint.pformat(payload))
             headers = {'Content-Type': 'application/x-www-form-urlencoded'}
             response = requests.post(url, data=payload, headers=headers, timeout=60)
             response.raise_for_status()
             data = response.json()
             _logger.info("Blackstone Refund Response: %s", pprint.pformat(data))
        except Exception as e:
             _logger.error("Blackstone Refund Error: %s", e)
             self._set_error(_("Could not connect to Blackstone for refund."))
             return

        if str(data.get('ResponseCode')) == '200':
             self.provider_reference = data.get('ServiceReferenceNumber')
             self._set_done()
        else:
             error_msg = data.get('Message') or _('Refund failed')
             if isinstance(data.get('Msg'), list):
                 error_msg += ": " + ", ".join(data.get('Msg'))
             self._set_error(error_msg)
