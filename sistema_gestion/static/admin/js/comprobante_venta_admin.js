if (window.django && window.django.jQuery) {
    const $ = django.jQuery;

    $(document).ready(function() {
        const inlineContainer = $('#items-group');
        if (!inlineContainer.length) return;

        // --- INTERFAZ ---
        if (inlineContainer.find('th.field-subtotal').length === 0) {
            inlineContainer.find('thead tr').append('<th class="field-subtotal">SUBTOTAL</th>');
        }
        inlineContainer.find('tbody tr').each(function() {
            if ($(this).find('td.field-subtotal').length === 0) {
                $(this).append('<td class="field-subtotal" style="font-weight: bold; text-align: right; padding-right: 1em;">-</td>');
            }
        });

        // --- FUNCIÓN DE CÁLCULO CENTRAL ---
        function actualizarCalculos() {
            const itemsData = [];
            // Recolectamos los datos de cada fila
            inlineContainer.find('tbody tr.dynamic-items').not('.empty-form').each(function() {
                const row = $(this);
                const articuloId = row.find('select[name$="-articulo"]').val();
                if (articuloId) {
                    itemsData.push({
                        articulo: articuloId,
                        cantidad: row.find('input[name$="-cantidad"]').val() || '0',
                        precio: row.find('input[name$="-precio_unitario_original"]').val() || '0',
                    });
                }
            });

            // Llamamos a nuestra nueva API para que el backend haga el trabajo pesado
            fetch(`/admin/ventas/comprobanteventa/api/calcular-totales/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': $('input[name="csrfmiddlewaretoken"]').val()
                },
                body: JSON.stringify({
                    items: itemsData,
                    // Enviamos también el tipo de comprobante, por si afecta los impuestos
                    tipo_comprobante: $('#id_tipo_comprobante').val()
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    console.error("Faro ERP (Error de cálculo):", data.error);
                    return;
                }

                // Actualizamos la sección "Totales" de arriba
                $('.field-subtotal .readonly').text(`$${data.subtotal}`);
                $('.field-total .readonly').text(`$${data.total}`);

                // Construimos el HTML para el desglose de impuestos
                let impuestosHtml = '<ul>';
                for (const [nombre, monto] of Object.entries(data.impuestos)) {
                    impuestosHtml += `<li><strong>${nombre}:</strong> $${monto}</li>`;
                }
                impuestosHtml += '</ul>';
                $('.field-impuestos_desglosados .readonly').html(impuestosHtml);

                // Actualizamos los subtotales por línea (opcional, pero buena UX)
                let i = 0;
                inlineContainer.find('tbody tr.dynamic-items').not('.empty-form').each(function() {
                    const row = $(this);
                    const cantidad = parseFloat(row.find('input[name$="-cantidad"]').val()) || 0;
                    const precio = parseFloat(row.find('input[name$="-precio_unitario_original"]').val()) || 0;
                    const subtotal = cantidad * precio;
                    row.find('.field-subtotal').text(`$${subtotal.toLocaleString('es-AR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`);
                    i++;
                });
            })
            .catch(error => console.error('Faro ERP (Error en Fetch):', error));
        }

        // --- MANEJADOR DE EVENTOS (GATILLOS) ---
        function handleArticuloChange(selectElement) {
            const articuloId = $(selectElement).val();
            const row = $(selectElement).closest('tr.dynamic-items');
            const cantidadInput = row.find('input[name$="-cantidad"]');
            const precioInput = row.find('input[name$="-precio_unitario_original"]');

            if (!articuloId) {
                precioInput.val('');
                cantidadInput.val('');
                actualizarCalculos();
                return;
            }

            fetch(`/admin/ventas/comprobanteventa/api/get-precio-articulo/${articuloId}/`)
                .then(response => response.json())
                .then(data => {
                    if (data.precio) {
                        precioInput.val(data.precio);
                        if (!cantidadInput.val()) {
                            cantidadInput.val('1');
                        }
                        actualizarCalculos(); // Llamada central
                    }
                })
                .catch(error => console.error('Faro ERP (Error):', error));
        }

        // --- LISTENERS ---
        inlineContainer.on('change', 'select[name$="-articulo"]', function() { handleArticuloChange(this); });
        $(document).on('formset:added', function(event, $row, formsetName) {
            if (formsetName === 'items') {
                if ($row.find('td.field-subtotal').length === 0) {
                     $row.append('<td class="field-subtotal" style="font-weight: bold; text-align: right; padding-right: 1em;">-</td>');
                }
                const selectElement = $row.find('select[name$="-articulo"]');
                setTimeout(() => { selectElement.on('change', function() { handleArticuloChange(this); }); }, 100);
            }
        });
        inlineContainer.on('input', 'input[name$="-cantidad"], input[name$="-precio_unitario_original"]', function() { actualizarCalculos(); });
        $('#id_tipo_comprobante').on('change', function() { actualizarCalculos(); }); // Recalcula si cambia el tipo

        actualizarCalculos(); // Cálculo inicial
    });
}