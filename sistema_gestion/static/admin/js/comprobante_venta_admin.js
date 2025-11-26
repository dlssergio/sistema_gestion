/* static/admin/js/comprobante_venta_admin.js - VERSIÓN DEFINITIVA */
'use strict';

window.addEventListener('DOMContentLoaded', function() {
    // Verificación de seguridad
    if (!window.django || !window.django.jQuery) return;
    const $ = django.jQuery;

    const inlineGroup = $('#items-group');
    if (!inlineGroup.length) return;

    console.log("🚀 Faro ERP: Comprobante Venta Script CARGADO.");

    // --- 1. FUNCIÓN DE CÁLCULO DE TOTALES (Llama al Backend) ---
    function actualizarCalculos() {
        const itemsData = [];

        // Recorremos las filas visibles
        inlineGroup.find('tr.dynamic-items').each(function() {
            const row = $(this);
            // Ignoramos filas eliminadas o vacías
            if (row.hasClass('empty-form') || row.find('.action-checkbox input').is(':checked')) return;

            const articuloId = row.find('select[name$="-articulo"]').val();
            if (articuloId) {
                itemsData.push({
                    articulo: articuloId,
                    cantidad: row.find('input[name$="-cantidad"]').val() || '0',
                    precio_monto: row.find('input[name$="-precio_unitario_original"]').val() || '0',
                    // Asumimos moneda base por defecto si no hay campo explícito en el frontend
                    // El backend lo manejará
                });
            }
        });

        // Llamada a la API de cálculo de totales
        fetch(`/admin/ventas/comprobanteventa/api/calcular-totales/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': $('input[name="csrfmiddlewaretoken"]').val()
            },
            body: JSON.stringify({
                items: itemsData,
                tipo_comprobante: $('#id_tipo_comprobante').val()
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error("❌ Error cálculo backend:", data.error);
                return;
            }

            // Actualizamos Totales Generales
            $('.field-subtotal .readonly').text(`${data.currency_symbol} ${data.subtotal}`);
            $('.field-total .readonly').text(`${data.currency_symbol} ${data.total}`);

            // Actualizamos Desglose de Impuestos
            let impuestosHtml = '<ul style="margin: 0; padding-left: 15px;">';
            for (const [nombre, monto] of Object.entries(data.impuestos)) {
                impuestosHtml += `<li><strong>${nombre}:</strong> ${data.currency_symbol} ${monto}</li>`;
            }
            impuestosHtml += '</ul>';
            $('.field-impuestos_desglosados .readonly').html(impuestosHtml);

            // Actualizamos subtotales por línea (Visual)
            // Nota: Esto asume que las filas están en orden.
            // Una implementación más estricta usaría IDs de línea, pero para el Admin esto basta.
            let i = 0;
            inlineGroup.find('tr.dynamic-items:not(.empty-form)').each(function() {
                if ($(this).find('.action-checkbox input').is(':checked')) return;

                const row = $(this);
                const cantidad = parseFloat(row.find('input[name$="-cantidad"]').val()) || 0;
                const precio = parseFloat(row.find('input[name$="-precio_unitario_original"]').val()) || 0;
                const subtotal = cantidad * precio;

                row.find('.field-subtotal').text(`$ ${subtotal.toLocaleString('es-AR', {minimumFractionDigits: 2})}`);
                i++;
            });
        })
        .catch(err => console.error("Error Fetch Totales:", err));
    }

    // --- 2. FUNCIÓN DE BÚSQUEDA DE PRECIO (Llama al Backend) ---
    async function handleArticuloChange(selectElement) {
        const $select = $(selectElement);
        const row = $select.closest('tr.dynamic-items');
        const articuloId = $select.val();

        const precioInput = row.find('input[name$="-precio_unitario_original"]');
        const cantidadInput = row.find('input[name$="-cantidad"]');

        // VALIDACIÓN 1: Cliente Obligatorio
        const clienteId = $('#id_cliente').val();
        if (!clienteId && articuloId) {
            alert("⚠️ Por favor, seleccione un CLIENTE primero para cargar la lista de precios correcta.");
            $select.val(null).trigger('change.select2'); // Limpiar selección
            return;
        }

        // Si borró el artículo, limpiamos
        if (!articuloId) {
            precioInput.val('0.00');
            actualizarCalculos();
            return;
        }

        console.log(`🔎 Buscando precio para Articulo ${articuloId} y Cliente ${clienteId}`);

        try {
            const url = `/admin/ventas/comprobanteventa/api/get-precio-articulo-cliente/${clienteId}/${articuloId}/`;
            const response = await fetch(url);

            if (response.ok) {
                const data = await response.json();

                // data debe devolver: { precio: "123.45", ... } o estructura PricingResult
                // Adaptamos según lo que devuelva tu vista 'get_precio_articulo_cliente'
                const precio = data.precio_venta_neto || data.precio || data.amount;

                if (precio) {
                    precioInput.val(precio);

                    // Default cantidad 1
                    if (!cantidadInput.val() || parseFloat(cantidadInput.val()) === 0) {
                        cantidadInput.val('1');
                    }

                    // Efecto Visual
                    precioInput.css({'background-color': '#d4edda', 'transition': '0.5s'});
                    setTimeout(() => precioInput.css('background-color', ''), 500);
                }
            }
        } catch (error) {
            console.error("❌ Error obteniendo precio:", error);
        } finally {
            actualizarCalculos();
        }
    }

    // --- 3. LISTENERS (PATRÓN ROBUSTO) ---

    // A. Cambio de Artículo (Select2)
    $(document).on('select2:select', 'select[name$="-articulo"]', function(e) {
        handleArticuloChange(this);
    });

    // B. Cambio de Artículo (Nativo / Fallback)
    $(document).on('change', 'select[name$="-articulo"]', function(e) {
        if (!$(this).data('select2')) {
            handleArticuloChange(this);
        }
    });

    // C. Recálculo de Totales al cambiar valores
    $(document).on('input change', 'input[name$="-cantidad"], input[name$="-precio_unitario_original"]', function() {
        // Debounce para no saturar
        clearTimeout(window.recalcTimer);
        window.recalcTimer = setTimeout(actualizarCalculos, 100);
    });

    // D. Cambio de Cliente -> Reiniciar Precios (Seguridad)
    $('#id_cliente').on('change', function() {
        // Filtramos filas que tengan un artículo seleccionado
        let articulosCargados = false;

        inlineGroup.find('tr.dynamic-items:not(.empty-form)').each(function() {
            // Verificar si hay valor en el select de artículo
            if ($(this).find('select[name$="-articulo"]').val()) {
                articulosCargados = true;
            }
        });

        if (articulosCargados) {
            if (confirm("⚠️ Ha cambiado el cliente. ¿Desea actualizar los precios de los artículos cargados?")) {
                inlineGroup.find('tr.dynamic-items:not(.empty-form)').each(function() {
                    const select = $(this).find('select[name$="-articulo"]');
                    if (select.val()) handleArticuloChange(select);
                });
            }
        }
    });

    // E. Inicialización de columnas
    if (inlineGroup.find('th.field-subtotal').length === 0) {
        inlineGroup.find('thead tr').append('<th class="field-subtotal">Subtotal</th>');
        inlineGroup.find('tbody tr.dynamic-items').append('<td class="field-subtotal"></td>');
    }

    // F. Inicialización al agregar fila
    $(document).on('formset:added', function(event, $row, formsetName) {
        $row.append('<td class="field-subtotal">-</td>');
    });

    // Cálculo inicial
    actualizarCalculos();
});