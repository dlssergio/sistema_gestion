// en static/admin/js/comprobante_venta_admin.js (Versión Final con jQuery)

if (window.django && window.django.jQuery) {
    const $ = django.jQuery;

    $(document).ready(function() {
        const inlineContainer = $('#items-group');
        if (!inlineContainer.length) { return; }

        if ($('.total-display').length === 0) {
            const totalDiv = $('<div class="total-display"></div>').css({
                'text-align': 'right', 'padding': '10px', 'font-weight': 'bold',
                'font-size': '1.2em', 'margin-top': '10px', 'border-top': '1px solid #eee'
            });
            inlineContainer.append(totalDiv);
        }

        function actualizarTotal() {
            let totalGeneral = 0;
            inlineContainer.find('.form-row').each(function() {
                const row = $(this);
                const cantidad = parseFloat(row.find('input[name$="-cantidad"]').val()) || 0;
                const precio = parseFloat(row.find('input[name$="-precio_unitario_original"]').val()) || 0;
                totalGeneral += cantidad * precio;
            });
            $('.total-display').text(`Total General: $${totalGeneral.toLocaleString('es-AR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`);
        }

        inlineContainer.on('change', '.field-articulo select', function() {
            const selectElement = $(this);
            const articuloId = selectElement.val();
            const row = selectElement.closest('.form-row');
            const precioInput = row.find('.field-precio_unitario_original input');

            if (!articuloId) {
                precioInput.val('');
                actualizarTotal();
                return;
            }

            fetch(`/ventas/api/get-precio-articulo/${articuloId}/`)
                .then(response => response.json())
                .then(data => {
                    if (data.precio) {
                        precioInput.val(data.precio);
                        actualizarTotal();
                    }
                })
                .catch(error => console.error('Error al obtener precio:', error));
        });

        inlineContainer.on('input', 'input[name$="-cantidad"], input[name$="-precio_unitario_original"]', function() {
            actualizarTotal();
        });

        actualizarTotal();
    });
}