/** @odoo-module */

import { PaymentForm } from "@payment/interactions/payment_form";
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { loadJS } from "@web/core/assets";

patch(PaymentForm.prototype, {
  /**
   * @override
   */
  _getPaymentFlow(radio) {
    if (this._getProviderCode(radio) === "blackstone") {
      return "direct";
    }
    return super._getPaymentFlow(...arguments);
  },

  /**
   * @override
   */
  async _processDirectFlow(
    providerCode,
    paymentOptionId,
    paymentMethodCode,
    processingValues,
  ) {
    if (providerCode !== "blackstone") {
      return super._processDirectFlow(...arguments);
    }

    const blackstoneForm = document.querySelector(".o_blackstone_inline_form");
    const raw3ds = blackstoneForm.getAttribute('data-blackstone-3ds-enabled');
    const is3dsEnabled = raw3ds === '1' || raw3ds === 'True';
    console.log("Blackstone 3DS Enabled:", is3dsEnabled, "Raw value:", raw3ds);

    const inputs = {
      card: blackstoneForm
        .querySelector("#card_number")
        .value.replace(/\s+/g, ""),
      month: blackstoneForm.querySelector("#exp_month").value,
      year: blackstoneForm.querySelector("#exp_year").value,
      cvc: blackstoneForm.querySelector("#cvc").value,
    };

    // 1. Validate Empty Fields
    if (!inputs.card || !inputs.month || !inputs.year || !inputs.cvc) {
      this._enableButton();
      this._displayErrorDialog(
        _t("Error de validación"),
        _t("Por favor, complete todos los campos de pago."),
      );
      return;
    }

    // 2. Validate Card Number (Luhn)
    if (!this._luhnCheck(inputs.card)) {
      this._enableButton();
      this._displayErrorDialog(
        _t("Error de validación"),
        _t("Número de tarjeta inválido."),
      );
      return;
    }

    // 3. Validate Expiry
    const currentYear = new Date().getFullYear() % 100;
    const currentMonth = new Date().getMonth() + 1;
    const expMonth = parseInt(inputs.month, 10);
    const expYear = parseInt(inputs.year, 10);

    if (expMonth < 1 || expMonth > 12) {
      this._enableButton();
      this._displayErrorDialog(_t("Error de validación"), _t("Mes inválido."));
      return;
    }
    if (
      expYear < currentYear ||
      (expYear === currentYear && expMonth < currentMonth)
    ) {
      this._enableButton();
      this._displayErrorDialog(
        _t("Error de validación"),
        _t("La tarjeta ha expirado."),
      );
      return;
    }

    // 4. Validate CVC
    if (inputs.cvc.length < 3 || inputs.cvc.length > 4 || isNaN(inputs.cvc)) {
      this._enableButton();
      this._displayErrorDialog(_t("Error de validación"), _t("CVC inválido."));
      return;
    }

    const processData = {
      reference: processingValues.reference,
      card_number: inputs.card,
      exp_month: inputs.month,
      exp_year: inputs.year,
      cvc: inputs.cvc,
      secure_data: "",
      secure_transaction_id: "",
    };

    // --- 3D Secure Flow ---
    if (is3dsEnabled) {
      try {
        // Load 3DS Library
        await loadJS("https://cdn.3dsintegrator.com/threeds.2.2.20231219.min.js");

        // Get 3DS Token
        const tokenData = await rpc("/payment/blackstone/get_3ds_token", {
          reference: processingValues.reference,
        });

        if (tokenData.error) {
          throw new Error(tokenData.error);
        }

        const verificationResult = await this._verify3DS(
          inputs,
          tokenData,
          processingValues,
        );

        if (
          verificationResult.status === "Y" ||
          verificationResult.status === "A"
        ) {
          processData.secure_data = verificationResult.authenticationValue;
          processData.secure_transaction_id =
            verificationResult.threeDsTransactionId;
        } else {
          this._enableButton();
          this._displayErrorDialog(
            _t("Autenticación fallida"),
            verificationResult.transStatusReasonDetail ||
              _t("No se pudo completar la verificación 3D Secure."),
          );
          return;
        }
      } catch (error) {
        this._enableButton();
        this._displayErrorDialog(
          _t("Error de 3D Secure"),
          error.message ||
            _t("Ocurrió un error durante la autenticación de seguridad."),
        );
        return;
      }
    }

    try {
      await rpc("/payment/blackstone/process", processData);
      window.location = "/payment/status";
    } catch (error) {
      this._displayErrorDialog(
        _t("Error de pago"),
        error.data ? error.data.message : _t("No pudimos procesar su pago."),
      );
    }
  },

  async _verify3DS(inputs, tokenData, processingValues) {
    return new Promise((resolve, reject) => {
      // Create hidden billing form for ThreeDS.js
      const tempForm = document.createElement("form");
      tempForm.id = "billing-form";
      tempForm.style.display = "none";

      const addField = (name, value, dataThreeds) => {
        const input = document.createElement("input");
        input.type = "text";
        input.name = name;
        input.value = value;
        input.setAttribute("data-threeds", dataThreeds);
        tempForm.appendChild(input);
      };

      addField("billing-card-amount", processingValues.amount, "amount");
      addField("billing-card-pan", inputs.card, "pan");
      addField("billing-card-month", inputs.month, "month");
      addField("billing-card-year", inputs.year, "year");
      addField("billing-card-cvv", inputs.cvc, "cvv");
      addField("billing-card-billing-post-code", "10400", "billingPostCode"); // Default or gather from form
      addField("billing-card-holder-name", "Customer", "cardHolderName"); 

      document.body.appendChild(tempForm);

      // Create Modal UI
      const overlay = document.createElement("div");
      overlay.id = "threeds-overlay";
      overlay.style.cssText =
        "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);z-index:9999;display:flex;align-items:center;justify-content:center;font-family:sans-serif;";

      const modal = document.createElement("div");
      modal.style.cssText =
        "background:#fff;padding:25px;border-radius:12px;width:480px;max-width:95%;text-align:center;box-shadow:0 15px 35px rgba(0,0,0,0.3);position:relative;";
      modal.innerHTML = `
            <h4 style="margin-top:0;margin-bottom:15px;color:#333;">Verificación de Seguridad</h4>
            <div id="threeds-container" style="width:420px;height:430px;margin:0 auto;border:1px solid #eee;border-radius:8px;overflow:hidden;background:#fafafa;display:flex;align-items:center;justify-content:center;position:relative;">
                <div id="threeds-loading" style="text-align:center;">
                    <div style="border:4px solid #f3f3f3;border-top:4px solid #3498db;border-radius:50%;width:30px;height:30px;animation:spin 1s linear infinite;margin:0 auto;"></div>
                    <p style="margin-top:10px;color:#666;">Cargando verificación...</p>
                </div>
            </div>
            <p style="margin-top:20px;font-size:15px;color:#d9534f;font-weight:bold;">
                Tiempo restante: <span id="threeds-timer">03:00</span>
            </p>
            <style>
                @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            </style>
        `;
      overlay.appendChild(modal);
      document.body.appendChild(overlay);

      const iframeId = "container-challenge-3ds-" + Date.now();
      const iframe = document.createElement("iframe");
      iframe.id = iframeId;
      iframe.style.cssText =
        "width:420px;height:430px;border:none;display:none;border-radius:8px;";
      document.getElementById("threeds-container").appendChild(iframe);

      const cleanup = () => {
        if (timerInterval) clearInterval(timerInterval);
        if (document.getElementById("threeds-overlay")) document.body.removeChild(overlay);
        if (document.getElementById("billing-form")) document.body.removeChild(tempForm);
        window.tds = undefined;
      };

      // Timer Logic (180 seconds)
      let timeRemaining = 180;
      const timerInterval = setInterval(() => {
        timeRemaining--;
        if (timeRemaining <= 0) {
          cleanup();
          reject(new Error(_t("La sesión de verificación ha expirado. Por favor, intente de nuevo.")));
        } else {
          const min = Math.floor(timeRemaining / 60).toString().padStart(2, "0");
          const sec = (timeRemaining % 60).toString().padStart(2, "0");
          const timerEl = document.getElementById("threeds-timer");
          if (timerEl) timerEl.textContent = `${min}:${sec}`;
        }
      }, 1000);

      try {
        iframe.onload = () => {
          const loading = document.getElementById("threeds-loading");
          if (loading) loading.style.display = "none";
          iframe.style.display = "block";
        };

        window.tds = new window.ThreeDS(
          "billing-form",
          tokenData.apiKey,
          tokenData.token,
          {
            endpoint: tokenData.endpoint,
            autoSubmit: false,
            showChallenge: true,
            popup: false,
            iframeId: iframeId,
            forcedTimeout: "180",
          },
        );

        window.tds.verify(
          (response) => {
            // Success handler logic matching WP snippet
            if (!response || (response.status !== "Y" && response.status !== "A")) {
              let msg = _t("La verificación no pudo completarse.");
              if (response && response.transStatusReasonDetail) {
                msg += ": " + response.transStatusReasonDetail;
              }
              cleanup();
              reject(new Error(msg));
              return;
            }

            if (window.tds.threeDsTransactionId) {
              response.threeDsTransactionId = window.tds.threeDsTransactionId;
            }
            cleanup();
            resolve(response);
          },
          (error) => {
            // Error handler logic matching WP snippet: only close if it's NOT a "no result yet" error
            let errorObj = error;
            if (typeof error === "string") {
              try { errorObj = JSON.parse(error); } catch (e) {}
            }
            const errorMessage = errorObj.error || errorObj.message || _t("Error durante la verificación.");
            console.log("3DS Verification Error:", errorMessage);

            if (errorMessage !== "No result found for transaction as yet. Please subscribe again") {
              cleanup();
              reject(new Error(errorMessage));
            } else {
                console.log("3DS: No hay resultado aún, continuando suscripción...");
                // Note: The library usually keeps polling or waiting if autoSubmit is false/challenge is active
            }
          },
          {
            amount: parseFloat(processingValues.amount),
            currency: "840", // USD
          },
        );
      } catch (e) {
        cleanup();
        reject(e);
      }
    });
  },

  _luhnCheck(val) {
    let checksum = 0;
    let j = 1;
    for (let i = val.length - 1; i >= 0; i--) {
      let calc = 0;
      calc = Number(val.charAt(i)) * j;
      if (calc > 9) {
        checksum = checksum + 1;
        calc = calc - 10;
      }
      checksum = checksum + calc;
      if (j == 1) {
        j = 2;
      } else {
        j = 1;
      }
    }
    return checksum % 10 == 0;
  },
});
