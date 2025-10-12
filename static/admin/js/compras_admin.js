// en static/admin/js/compras_admin.js (VERSIÓN FINAL PARA MONEDAS PERSONALIZADAS)

window.addEventListener('DOMContentLoaded', function() {
    const $ = django.jQuery;

    $(document.body).on('change', '.related-widget-wrapper select[name$="-articulo"]', async function() {
        const articuloId = $(this).val();
        const row = $(this).closest('tr.dynamic-items');

        const costoMontoInput = row.find('input[name$="-precio_costo_unitario_0"]');
        const costoMonedaSelect = row.find('select[name$="-precio_costo_unitario_1"]');
        const cantidadInput = row.find('input[name$="-cantidad"]');

        if (!articuloId) {
            costoMontoInput.val('');
            return;
        }

        if (costoMontoInput.length === 0 || costoMonedaSelect.length === 0) {
            console.error("No se encontraron los campos de costo en la fila.");
            return;
        }

        try {
            const url = `/admin/compras/comprobantecompra/get-articulo-costo/${articuloId}/`;
            const response = await fetch(url);

            if (!response.ok) {
                console.error("Error en la respuesta del servidor al obtener el costo.");
                return;
            }

            const articuloData = await response.json();

            if (articuloData && articuloData.amount !== undefined) {
                costoMontoInput.val(articuloData.amount);

                // --- CAMBIO CLAVE ---
                // Leemos el 'currency_id' de la respuesta JSON
                const currencyId = articuloData.currency_id;
                if (currencyId) {
                    // Asignamos el ID directamente al select. ¡Esto seleccionará la opción correcta!
                    costoMonedaSelect.val(currencyId).trigger('change');
                }

                if (cantidadInput.length > 0 && !cantidadInput.val()) {
                    cantidadInput.val('1');
                }
            }
        } catch (error) {
            console.error('Error al procesar la solicitud del artículo:', error);
        }
    });
});