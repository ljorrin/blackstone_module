from odoo import api, fields, models, _
from odoo.http import request
from odoo.exceptions import ValidationError
import logging
import requests

_logger = logging.getLogger(__name__)

class PaymentProviderBlackstone(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(selection_add=[('blackstone', "Blackstone Online Payment Gateway")], ondelete={'blackstone': 'set default'})

    # Basic Configuration
    blackstone_description = fields.Text(
        string="Description", 
        default="Pay securely with your credit card.",
        help="Payment description shown to customers during checkout."
    )

    # API Credentials
    blackstone_api_username = fields.Char(
        string="Username", 
        help="This is the username provided by Blackstone when you signed up for an account."
    )
    blackstone_api_password = fields.Char(
        string="Password", 
        help="This is the password provided by Blackstone when you signed up for an account."
    )
    blackstone_api_mid = fields.Char(
        string="MID", 
        help="This is the MID code provided by Blackstone when you signed up for an account."
    )
    blackstone_api_cid = fields.Char(
        string="CID", 
        help="This is the CID code provided by Blackstone when you signed up for an account."
    )

    # App Configuration
    blackstone_app_type = fields.Char(
        string="App Type", 
        help="This is the App Type provided by Blackstone when you signed up for an account."
    )
    blackstone_app_key = fields.Char(
        string="App Key", 
        help="This is the App Key provided by Blackstone when you signed up for an account."
    )

    # Environment Settings
    blackstone_test_mode = fields.Boolean(
        string="Enable Test Mode", 
        help="This is the sandbox of the gateway."
    )
    blackstone_3ds_test_mode = fields.Boolean(
        string="Enable 3D Secure Test Mode", 
        help="This is the sandbox of 3D Secure."
    )

    # Display Labels
    blackstone_label_surcharge = fields.Char(
        string="Surcharge Label", 
        default="Surcharge", 
        help="This is the name that will be shown to your customers wherever a surcharge is applied (for example, in the order summary or invoice)."
    )
    blackstone_label_dual_pricing = fields.Char(
        string="Dual Pricing Label", 
        default="Dual pricing", 
        help="This is the name that will be shown to your customers wherever the card difference (dual pricing) is applied. For example, in the order summary or invoice."
    )

    # Merchant Settings (Synced from Gateway)
    blackstone_surcharge_enabled = fields.Boolean(string="Surcharge Enabled", readonly=True)
    blackstone_surcharge_percent = fields.Float(string="Surcharge Percent", readonly=True)
    blackstone_card_difference_enabled = fields.Boolean(string="Card Difference Enabled", readonly=True)
    blackstone_card_difference_percent = fields.Float(string="Card Difference Percent", readonly=True)
    blackstone_ach_enabled = fields.Boolean(string="ACH Enabled", readonly=True) 
    blackstone_3ds_enabled = fields.Boolean(string="3D Secure Enabled", readonly=True, help="Automatically synced from Blackstone.")

    def action_blackstone_sync_settings(self):
        self.ensure_one()
        settings = self._blackstone_get_merchant_settings()
        if settings:
            self.write({
                'blackstone_surcharge_enabled': settings.get('SurchargeEnabled', False),
                'blackstone_surcharge_percent': float(settings.get('SurchargePercent', 0.0)),
                'blackstone_card_difference_enabled': settings.get('CardDifferenceEnabled', False),
                'blackstone_card_difference_percent': float(settings.get('CardDifferencePercent', 0.0)),
                'blackstone_3ds_enabled': settings.get('ThreeDSecureEnabled', False),
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Settings Synced"),
                    'message': _("Merchant settings have been successfully updated from Blackstone."),
                    'sticky': False,
                    'type': 'success',
                }
            }

    def _blackstone_get_api_url(self):
        base_url = "https://services.bmspay.com"
        if self.blackstone_test_mode:
             return f"{base_url}/api"
        return f"{base_url}/api"

    def _blackstone_get_merchant_settings(self):
        self.ensure_one()
        url = f"{self._blackstone_get_api_url()}/BusinessSettings"
        payload = self._blackstone_prepare_credential_data(for_3ds=True)
        
        _logger.info("Blackstone Merchant Settings Request to %s | Payload: %s", url, payload)
        
        try:
            response = requests.post(url, data=payload, timeout=45)
            _logger.info("Blackstone Merchant Settings Response Status: %s | Content: %s", response.status_code, response.text)
            response.raise_for_status()
            data = response.json()
            return data
        except Exception as e:
            _logger.error("Blackstone Merchant Settings Error: %s", e)
            raise ValidationError(_("Could not connect to Blackstone to sync settings. Please check your credentials and try again. Technical details: %s") % e)

    def _blackstone_prepare_credential_data(self, for_3ds=False):
        """ Replicates PHP prepare_credential_data logic. """
        self.ensure_one()
        
        # Sandbox credentials from PHP if test mode is active
        if for_3ds and self.blackstone_3ds_test_mode:
            return {
                "mid": "98208",
                "UserName": "617D46A6-3A1A-4A67-850A-89F7E4F48049",
                "Password": "CYC-4, LLC",
                "AppType": "11200",
                "AppKey": "563C17A4-A4E3-4A6F-BBF6-FC8B8B8E7F9F",
                "cid": "6310",
                "IpAddress": request.httprequest.remote_addr if request else '127.0.0.1',
                "Source": "ApiClient",
                "UserTest": "True"
            }
        
        # Standard Environment settings (Used for Payment/BusinessSettings)
        is_test = self.state == 'test' or self.blackstone_test_mode
        
        # If standard test mode is on, use defaults from PHP
        if is_test:

            return {
                "mid": "76074",
                "UserName": "nicolas",
                "Password": "password1",
                "AppType": "1",
                "AppKey": "12345",
                "cid": "260",
                "IpAddress": request.httprequest.remote_addr if request else '127.0.0.1',
                "Source": "ApiClient",
                "UserTest": "True"
            }

        return {
            "mid": self.blackstone_api_mid,
            "UserName": self.blackstone_api_username,
            "Password": self.blackstone_api_password,
            "AppType": self.blackstone_app_type,
            "AppKey": self.blackstone_app_key,
            "cid": self.blackstone_api_cid,
            "IpAddress": request.httprequest.remote_addr if request else '127.0.0.1',
            "Source": "ApiClient",
            "UserTest": "False"
        }

    def _blackstone_get_token_3ds(self):
        """ Gets ApiKey and Token for 3D Secure session. """
        self.ensure_one()
        url = f"{self._blackstone_get_api_url()}/Auth/TokenThreeDS"
        payload = self._blackstone_prepare_credential_data(for_3ds=True)
        
        try:
            _logger.info("Blackstone 3DS Token Request to %s", url)
            response = requests.post(url, data=payload, timeout=45)
            response.raise_for_status()
            data = response.json()
            return {
                'apiKey': data.get('ApiKey', ''),
                'token': data.get('Token', ''),
                'endpoint': 'https://api-sandbox.3dsintegrator.com/v2.2' if self.blackstone_3ds_test_mode else 'https://api.3dsintegrator.com/v2.2'
            }
        except Exception as e:
            _logger.error("Blackstone 3DS Token Error: %s", e)
            return {'error': str(e)}

    def _compute_feature_support_fields(self):
        """ Override of `payment` to enable feature support for Blackstone. """
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'blackstone').update({
            'support_refund': 'partial',
            'support_tokenization': True,
        })
