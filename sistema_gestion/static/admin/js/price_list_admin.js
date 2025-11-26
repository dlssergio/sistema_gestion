/* static/admin/js/price_list_admin.js - VERSIÓN DEFINITIVA */
'use strict';

window.addEventListener('load', function() {
    // Usamos el jQuery que trae Django
    const $ = django.jQuery;
    console.log("🚀 Faro ERP: Script de Lista de Precios CARGADO.");

    function actualizarPrecio(selectElement) {
        const $select = $(selectElement);
        const productId = $select.val();

        const $row = $select.closest('.form-row');
        const $priceInput = $row.find('input[name$="-price_monto"]');

        // Si se borró la selección, limpiamos el precio
        if (!productId) {
            $priceInput.val('');
            return;
        }

        console.log("🔎 Faro ERP: Producto cambiado ID:", productId);

        const url = `/admin/ventas/pricelist/api/get-precio-articulo/${productId}/`;

        $.ajax({
            url: url,
            dataType: 'json',
            success: function(data) {
                console.log("✅ Faro ERP: Datos recibidos:", data);

                const valorRecibido = data.precio || data.costo;

                if (valorRecibido) {
                    // CAMBIO CRÍTICO: Sobreescribimos SIEMPRE al cambiar de producto.
                    // Ya no validamos si estaba vacío, porque al cambiar de producto
                    // el usuario espera ver el precio del nuevo.

                    // Convertimos a float para quitar ceros innecesarios si se desea,
                    // o lo dejamos como string para respetar formato API.
                    $priceInput.val(valorRecibido);

                    // Efecto visual verde intenso para confirmar cambio
                    $priceInput.css({'background-color': '#d4edda', 'transition': '0.1s'});
                    setTimeout(() => $priceInput.css({'background-color': '', 'transition': '1s'}), 500);

                    console.log("✅ Campo actualizado con:", valorRecibido);
                }
            },
            error: function(xhr, status, error) {
                console.error("❌ Faro ERP Error API:", error);
                // Si falla, no limpiamos el campo por si el usuario quiere ponerlo a mano
            }
        });
    }

    // --- LISTENERS ---
    $(document).on('select2:select', 'select[name$="-product"]', function(e) {
        actualizarPrecio(this);
    });

    $(document).on('change', 'select[name$="-product"]', function(e) {
        // Evitamos doble disparo si es select2 (el evento change a veces salta después)
        if (!$(this).data('select2')) {
            actualizarPrecio(this);
        }
    });
});