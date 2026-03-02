{
    'name': 'Blackstone Payment Gateway',
    'version': '1.7',
    'category': 'Accounting/Payment Providers',
    'summary': 'Integración con Blackstone Online Payment Gateway',
    'description': """
Integración completa con Blackstone Online Payment Gateway para Odoo.

Características principales:
- Pagos seguros con tarjeta de crédito/débito.
- Soporte para 3D Secure 2.0 (Autenticación fuerte de cliente SCA).
- Soporte para recargos (Surcharges) y Dual Pricing sincronizados directamente desde Blackstone.
- Soporte para reembolsos (Refunds) totales y parciales desde la interfaz de Odoo.
- Tokenización de tarjetas para pagos recurrentes o futuros.
- Configuración simplificada y automatizada de diarios contables.
    """,
    'author': "Blackstone",
    'depends': ['payment', 'website', 'website_sale'],
    'data': [
        'views/payment_blackstone_templates.xml',
        'data/payment_provider_data.xml',
        'data/product_data.xml',
        'views/payment_provider_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'blackstone_payment/static/src/js/blackstone.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
    'license': 'LGPL-3',
}
