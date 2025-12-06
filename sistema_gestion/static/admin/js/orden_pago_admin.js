/* static/admin/js/orden_pago_admin.js - VERSIÓN FINAL ENTERPRISE */
'use strict';

window.addEventListener('DOMContentLoaded', function() {
    if (!window.django || !window.django.jQuery) return;
    const $ = django.jQuery;

    const inlineGroup = $('#imputaciones-group');
    if (!inlineGroup.length) return;

    console.log("🚀 Faro ERP: Orden Pago Script Cargado.");

    function fetchComprobanteInfo(selectElement) {
        const $select = $(selectElement);
        const comprobanteId = $select.val();
        const $row = $select.closest('tr'); // La fila actual

        // Inputs y Campos Visuales
        const $montoInput = $row.find('input[name$="-monto_imputado"]');
        // Buscamos la celda que tiene la clase del campo readonly
        const $totalDisplay = $row.find('.field-total_original_comprobante p, .field-total_original_comprobante');

        if (!comprobanteId) {
            $montoInput.val('');
            $totalDisplay.text('-');
            return;
        }

        // Efecto de carga visual
        $totalDisplay.css('opacity', '0.5');

        $.ajax({
            url: `/admin/compras/ordenpago/api/get-comprobante-info/${comprobanteId}/`,
            dataType: 'json',
            success: function(data) {
                if (data.saldo) {
                    // 1. Lógica Inteligente: Solo rellenar si está vacío o es 0
                    const currentVal = parseFloat($montoInput.val()) || 0;
                    if (currentVal === 0) {
                        $montoInput.val(data.saldo);
                        // Feedback visual verde
                        $montoInput.css({'background-color': '#d4edda', 'transition': '0.5s'});
                        setTimeout(() => $montoInput.css('background-color', ''), 1000);
                    }

                    // 2. ACTUALIZAR COLUMNA NO EDITABLE (TOTAL ORIGINAL)
                    // Django renderiza los readonly dentro de un <p> o directo en el td
                    if ($totalDisplay.length) {
                        // Formateamos como moneda
                        $totalDisplay.text(`$ ${parseFloat(data.total).toLocaleString('es-AR', {minimumFractionDigits: 2})}`);
                        $totalDisplay.css({'font-weight': 'bold', 'color': '#555', 'opacity': '1'});
                    }
                }
            },
            error: function() {
                $totalDisplay.text('Error');
            }
        });
    }

    // Listeners Robustos
    $(document).on('select2:select', 'select[name$="-comprobante"]', function() { fetchComprobanteInfo(this); });
    $(document).on('change', 'select[name$="-comprobante"]', function() {
        if (!$(this).data('select2')) fetchComprobanteInfo(this);
    });
});