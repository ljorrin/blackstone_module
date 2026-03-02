import logging
from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _send_order_confirmation_mail(self):
        """
        Override to prevent crashing if Wkhtmltopdf is missing.
        The payment flow relies on action_confirm completing successfully.
        """
        try:
            return super(SaleOrder, self)._send_order_confirmation_mail()
        except UserError as e:
            if "Wkhtmltopdf" in str(e):
                _logger.warning("Blackstone: Suppressed Wkhtmltopdf error during order confirmation. Email not sent, but order will be confirmed.")
                return False
            raise e
        except Exception as e:
            # We don't want to suppress all errors, but for this specific flow debugging, 
            # let's be careful. For now only target the known PDF error.
            raise e
