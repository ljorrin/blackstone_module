# Blackstone Online Payment Gateway for Odoo

Este módulo integra la pasarela de pagos de **Blackstone** con Odoo, permitiendo transacciones seguras con tarjeta de crédito/débito, gestión de recargos (Surcharges/Dual Pricing) y reembolsos integrados.

## 🚀 Características Principales

- **Pagos Seguros**: Integración con la API de Blackstone para procesar ventas.
- **3D Secure 2.0**: Capa de seguridad adicional con autenticación dinámica mediante Iframe, compatible con estándares SCA.
- **Dual Pricing / Surcharges**: Cálculo automático de recargos por uso de tarjeta, sincronizado con el pedido de venta.
- **Gestión de Reembolsos**: Permite realizar reembolsos totales o parciales directamente desde el registro de pago en Odoo.
- **Tokenización**: Opción para que los clientes guarden sus tarjetas de forma segura para compras futuras (vía tokens).
- **Configuración Automatizada**: Scripts de migración que configuran el diario de pagos y métodos técnicos de forma automática.

## 📋 Requisitos Previos

- **Odoo**: Versión 17.0 o superior (compatible hasta v20.0).
- **Librerías Python**: `requests` (para comunicación con la API).
- **HTTPS**: Es altamente recomendable que la instancia de Odoo cuente con SSL (HTTPS) para la seguridad de las transacciones.
- **Credenciales Blackstone**: AppKey, Password, UserName, MID y CID proporcionados por Blackstone.

---

## 🛠️ Guía de Instalación y Migración

### 1. Preparación del Sistema

Asegúrese de que la librería `requests` esté disponible en el entorno de Odoo:

```bash
pip install requests
```

### 2. Despliegue del Módulo

1. Copie la carpeta `blackstone_payment` en su directorio de `addons`.
2. Asegúrese de que la ruta esté en el `addons_path` de su archivo `odoo.conf`.
   ```ini
   addons_path = /opt/odoo/addons, /opt/odoo/custom_addons
   ```

### 3. Instalación en la Interfaz

1. Reinicie el servicio de Odoo.
2. Active el **Modo Desarrollador** (Ajustes -> Activar modo desarrollador).
3. Vaya al menú **Aplicaciones**.
4. Haga clic en el botón superior **Actualizar lista de aplicaciones**.
5. Busque "Blackstone" e instale el módulo `blackstone_payment`.

---

## ⚙️ Configuración del Proveedor

Una vez instalado, configure el proveedor siguiendo estos pasos:

1. Vaya a **Contabilidad -> Configuración -> Proveedores de Pago**.
2. Busque y abra **Blackstone**.
3. **Estado**: Cambie a `Modo de Prueba` para validar o `Habilitado` para producción.
4. **Credenciales**: Ingrese los datos proporcionados por Blackstone en la pestaña correspondiente.
5. **Configuración de Reembolsos**: El soporte para reembolsos parciales está habilitado por defecto a nivel de código.

---

## 🔍 Resolución de Problemas (Troubleshooting)

### El botón de Reembolso no aparece

- Verifique que el pago esté en estado **Publicado (Posted)**.
- Asegúrese de que el proveedor Blackstone esté en estado `Enabled` o `Test Mode`.
- El botón solo aparece si el pago se realizó a través de este proveedor y tiene una transacción vinculada exitosa.

### Error: "Please define a payment method line on your payment"

- Este módulo incluye un script que intenta corregir esto automáticamente al instalar/actualizar.
- Si persiste, vaya al **Diario de Banco** y en la pestaña de **Pagos Entrantes**, añada manualmente una línea con el método `Blackstone`.

### Logs de Transacción

Para ver qué está pasando con una transacción específica, revise los logs de Odoo (`odoo.log`). El módulo registra las peticiones y respuestas de la API de Blackstone con el prefijo `Blackstone Refund Request/Response`.

---

## 👨‍💻 Información Técnica para Administradores

- **Modelos Heredados**:
  - `payment.provider`: Configuración de la API y lógica de soporte de funciones.
  - `payment.transaction`: Lógica de envío de pagos y reembolsos.
  - `account.payment`: Integración de la UI para reembolsos.
- **Seguridad**: El módulo no almacena números de tarjeta completos en la base de datos de Odoo; utiliza tokens si la opción está habilitada.
- **Capa 3DS**:
  - **Sincronización Automática**: El flag de 3DS se sincroniza desde los ajustes del Merchant en Blackstone al pulsar "Sync Settings".
  - **Iframe Dinámico**: Modal de autenticación con temporizador de 3 minutos (180s) y manejo de desafíos prolongados (polling).
  - **Compatibilidad**: Soporte para MID de prueba y entornos de sandbox.

---

_Módulo desarrollado por el equipo de desarrollo de Blackstone._
