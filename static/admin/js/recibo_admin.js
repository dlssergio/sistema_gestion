/* static/admin/js/recibo_admin.js - VERSIÓN COMPLETA (CON AUTO-BALANCEO) */
'use strict';

window.addEventListener('DOMContentLoaded', function() {
    if (!window.django || !window.django.jQuery) return;
    const $ = django.jQuery;

    // Detectamos si estamos en la pantalla de Recibos revisando si existe el grupo de imputaciones
    const inlineGroup = $('#imputaciones-group');
    if (!inlineGroup.length) return;

    console.log("🚀 Faro ERP: Recibo Script Inteligente Cargado.");

    // --- 1. LÓGICA DE AUTOCOMPLETADO DE FACTURA ---
    // Trae el saldo pendiente y el total original al seleccionar un comprobante
    function fetchFacturaInfo(selectElement) {
        const $select = $(selectElement);
        const comprobanteId = $select.val();
        const $row = $select.closest('tr');

        const $montoInput = $row.find('input[name$="-monto_imputado"]');
        // Buscamos el campo de solo lectura (que suele estar en un <p> dentro de un div .field-...)
        const $totalDisplay = $row.find('.field-total_original_display p, .field-total_original_display');

        if (!comprobanteId) {
            $montoInput.val('');
            if ($totalDisplay.length) $totalDisplay.text('-');
            return;
        }

        // Consultamos API de Ventas
        $.ajax({
            url: `/admin/ventas/recibo/api/get-comprobante-info/${comprobanteId}/`,
            dataType: 'json',
            success: function(data) {
                if (data.saldo) {
                    // Solo llenamos si está vacío o es 0 (para no pisar ediciones manuales o el auto-balanceo)
                    const currentVal = parseFloat($montoInput.val()) || 0;
                    if (currentVal === 0) {
                        $montoInput.val(data.saldo);

                        // Efecto visual verde
                        $montoInput.css({'background-color': '#d4edda', 'transition': '0.5s'});
                        setTimeout(() => $montoInput.css('background-color', ''), 1000);
                    }

                    // Mostrar Total Original visualmente
                    if ($totalDisplay.length) {
                        $totalDisplay.text(`$ ${parseFloat(data.total).toLocaleString('es-AR', {minimumFractionDigits: 2})}`);
                        $totalDisplay.css({'font-weight': 'bold', 'color': '#555'});
                    }
                }
            },
            error: function(err) {
                console.error("Error obteniendo info de factura:", err);
            }
        });
    }

    // --- 2. LÓGICA DE AUTO-BALANCEO (NUEVO) ---
    // Si cargo valores de pago, ajustar automáticamente la imputación si hay una sola factura.
    // Esto es clave para la "Venta de Contado".
    function balancearImputacion() {
        // A. Sumar todos los valores de pago cargados (Efectivo + Cheques, etc.)
        let totalValores = 0;
        $('#valores-group').find('tr:not(.empty-form) input[name$="-monto"]').each(function() {
            totalValores += parseFloat($(this).val()) || 0;
        });

        // B. Ver cuántas facturas estamos pagando
        const filasImputacion = $('#imputaciones-group').find('tr:not(.empty-form)');

        // ESTRATEGIA: Si hay UNA sola factura en la lista, asumimos que el pago es para ella.
        if (filasImputacion.length === 1 && totalValores > 0) {
            const inputImputado = filasImputacion.find('input[name$="-monto_imputado"]');

            // Solo actualizamos si el valor es diferente para dar feedback visual
            if (parseFloat(inputImputado.val()) !== totalValores) {
                inputImputado.val(totalValores);

                // Feedback visual (parpadeo amarillo para indicar "te ayudé con esto")
                inputImputado.css({'background-color': '#fff3cd', 'transition': '0.5s'});
                setTimeout(() => inputImputado.css('background-color', ''), 500);
            }
        }

        // Actualizar también el total visual del recibo
        $('.field-monto_total .readonly').text(totalValores.toFixed(2));
    }

    // --- 3. LISTENERS ---

    // A. Cambio de Comprobante (Select2)
    $(document).on('select2:select', 'select[name$="-comprobante"]', function() {
        fetchFacturaInfo(this);
    });

    // B. Cambio de Comprobante (Nativo/Fallback)
    $(document).on('change', 'select[name$="-comprobante"]', function() {
        if (!$(this).data('select2')) fetchFacturaInfo(this);
    });

    // C. Cambio en los montos de pago (Dispara el balanceo)
    $(document).on('input', 'input[name$="-monto"]', function() {
        // Usamos un pequeño timeout (debounce) para no calcular en cada tecla
        clearTimeout(window.balanceTimer);
        window.balanceTimer = setTimeout(balancearImputacion, 100);
    });

});