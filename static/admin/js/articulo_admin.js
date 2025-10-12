// static/admin/js/articulo_admin.js (VERSIÓN FINAL PARA DJANGO-MONEY Y MONEDAS PERSONALIZADAS)

window.addEventListener('DOMContentLoaded', (event) => {
    const cotizacionesElement = document.getElementById('cotizaciones-json');
    const tasasImpuestosElement = document.getElementById('tasas-impuestos-json');
    if (!cotizacionesElement || !tasasImpuestosElement) { return; }

    const cotizaciones = JSON.parse(cotizacionesElement.textContent);
    const tasasImpuestos = JSON.parse(tasasImpuestosElement.textContent);

    const camposPrecios = {
        costoMonto: document.querySelector('#id_precio_costo_0'),
        costoMoneda: document.querySelector('#id_precio_costo_1'),
        utilidad: document.querySelector('#id_utilidad'),
        ventaMonto: document.querySelector('#id_precio_venta_0'),
        ventaMoneda: document.querySelector('#id_precio_venta_1'),
        impuesto: document.querySelector('#id_impuesto'),
        precioFinal: document.querySelector('.field-precio_final_form .readonly'),
    };

    let lastModified = null;

    function calcularVenta() {
        if (lastModified !== 'venta') {
            const cotizacionCosto = parseFloat(cotizaciones[camposPrecios.costoMoneda.value]) || 1;
            const costoMonto = parseFloat(camposPrecios.costoMonto.value) || 0;
            const utilidad = parseFloat(camposPrecios.utilidad.value) || 0;
            const cotizacionVenta = parseFloat(cotizaciones[camposPrecios.ventaMoneda.value]) || 1;

            const costoEnBase = costoMonto * cotizacionCosto;
            const ventaEnBase = costoEnBase * (1 + (utilidad / 100));

            if (cotizacionVenta > 0) {
                const nuevaVentaMonto = ventaEnBase / cotizacionVenta;
                camposPrecios.ventaMonto.value = nuevaVentaMonto.toFixed(2);
            }
            actualizarPrecioFinal();
        }
    }

    function calcularUtilidad() {
        if (lastModified !== 'utilidad') {
            const cotizacionCosto = parseFloat(cotizaciones[camposPrecios.costoMoneda.value]) || 1;
            const costoMonto = parseFloat(camposPrecios.costoMonto.value) || 0;
            const cotizacionVenta = parseFloat(cotizaciones[camposPrecios.ventaMoneda.value]) || 1;
            const ventaMonto = parseFloat(camposPrecios.ventaMonto.value) || 0;

            const costoEnBase = costoMonto * cotizacionCosto;
            const ventaEnBase = ventaMonto * cotizacionVenta;

            if (costoEnBase > 0) {
                const nuevaUtilidad = ((ventaEnBase / costoEnBase) - 1) * 100;
                camposPrecios.utilidad.value = nuevaUtilidad.toFixed(2);
            } else {
                camposPrecios.utilidad.value = (0).toFixed(2);
            }
            actualizarPrecioFinal();
        }
    }

    function actualizarPrecioFinal() {
        const cotizacionVenta = parseFloat(cotizaciones[camposPrecios.ventaMoneda.value]) || 1;
        const ventaMonto = parseFloat(camposPrecios.ventaMonto.value) || 0;
        const ventaEnBase = ventaMonto * cotizacionVenta;
        const tasaImpuesto = parseFloat(tasasImpuestos[camposPrecios.impuesto.value]) || 0;
        const precioFinal = ventaEnBase * (1 + (tasaImpuesto / 100));

        camposPrecios.precioFinal.textContent = `$${precioFinal.toLocaleString('es-AR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    }

    // Event Listeners
    camposPrecios.costoMonto.addEventListener('input', () => { lastModified = 'utilidad'; calcularVenta(); });
    camposPrecios.costoMoneda.addEventListener('change', () => { lastModified = 'utilidad'; calcularVenta(); });
    camposPrecios.utilidad.addEventListener('input', () => { lastModified = 'utilidad'; calcularVenta(); });

    camposPrecios.ventaMonto.addEventListener('input', () => { lastModified = 'venta'; calcularUtilidad(); });
    camposPrecios.ventaMoneda.addEventListener('change', () => { lastModified = 'utilidad'; calcularVenta(); });

    camposPrecios.impuesto.addEventListener('change', actualizarPrecioFinal);

    // Lógica de visibilidad de stock (sin cambios)
    const administraStockCheckbox = document.querySelector('#id_administra_stock');
    const stockFieldSelectors = [
        '.field-unidad_medida', '.form-row.field-stock_minimo',
        '.form-row.field-stock_maximo', '.form-row.field-punto_pedido', '#stockarticulo_set-group'
    ];

    function toggleStockFields() {
        if (!administraStockCheckbox) return;
        const isStockManaged = administraStockCheckbox.checked;
        stockFieldSelectors.forEach(selector => {
            const field = document.querySelector(selector);
            if (field) {
                field.style.display = isStockManaged ? '' : 'none';
            }
        });
    }

    if (administraStockCheckbox) {
        administraStockCheckbox.addEventListener('change', toggleStockFields);
        toggleStockFields();
    }

    actualizarPrecioFinal();
});