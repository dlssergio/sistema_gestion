window.addEventListener('DOMContentLoaded', (event) => {
    const cotizacionesElement = document.getElementById('cotizaciones-json');
    const tasasImpuestosElement = document.getElementById('tasas-impuestos-json');
    if (!cotizacionesElement || !tasasImpuestosElement) { return; }

    const cotizaciones = JSON.parse(cotizacionesElement.textContent);
    const reglasImpuesto = JSON.parse(tasasImpuestosElement.textContent);

    const campos = {
        costoMonto: document.querySelector('#id_precio_costo_0'),
        costoMoneda: document.querySelector('#id_precio_costo_1'),
        utilidad: document.querySelector('#id_utilidad'),
        ventaMonto: document.querySelector('#id_precio_venta_0'),
        ventaMoneda: document.querySelector('#id_precio_venta_1'),
        impuesto: document.querySelector('#id_impuesto'), // <<< NUEVO: El campo de selección de impuesto
        precioFinal: document.querySelector('.field-precio_final_form .readonly'),
    };

    let lastModified = null;

    function calcularVenta() {
        if (lastModified === 'venta') return;
        const cotizacionCosto = parseFloat(cotizaciones[campos.costoMoneda.value]) || 1;
        const costoMonto = parseFloat(campos.costoMonto.value) || 0;
        const utilidad = parseFloat(campos.utilidad.value) || 0;
        const cotizacionVenta = parseFloat(cotizaciones[campos.ventaMoneda.value]) || 1;

        const costoEnBase = costoMonto * cotizacionCosto;
        const ventaEnBase = costoEnBase * (1 + (utilidad / 100));

        if (cotizacionVenta > 0) {
            campos.ventaMonto.value = (ventaEnBase / cotizacionVenta).toFixed(2);
        }
        actualizarPrecioFinal();
    }

    function calcularUtilidad() {
        if (lastModified === 'utilidad') return;
        const cotizacionCosto = parseFloat(cotizaciones[campos.costoMoneda.value]) || 1;
        const costoMonto = parseFloat(campos.costoMonto.value) || 0;
        const cotizacionVenta = parseFloat(cotizaciones[campos.ventaMoneda.value]) || 1;
        const ventaMonto = parseFloat(campos.ventaMonto.value) || 0;

        const costoEnBase = costoMonto * cotizacionCosto;
        const ventaEnBase = ventaMonto * cotizacionVenta;

        if (costoEnBase > 0) {
            campos.utilidad.value = (((ventaEnBase / costoEnBase) - 1) * 100).toFixed(2);
        } else {
            campos.utilidad.value = (0).toFixed(2);
        }
        actualizarPrecioFinal();
    }

    function actualizarPrecioFinal() {
        const ventaMonto = parseFloat(campos.ventaMonto.value) || 0;
        let totalConImpuestos = ventaMonto;

        const impuestoSeleccionadoId = campos.impuesto.value;
        if (impuestoSeleccionadoId) {
            const regla = reglasImpuesto.find(r => r.id == impuestoSeleccionadoId);
            if (regla) {
                const tasa = parseFloat(regla.tasa);
                totalConImpuestos = ventaMonto * (1 + (tasa / 100));
            }
        }

        // Asumiendo que el precio de venta es en ARS para el display final
        campos.precioFinal.textContent = `$${totalConImpuestos.toLocaleString('es-AR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    }

    // Event Listeners
    campos.costoMonto.addEventListener('input', () => { lastModified = 'utilidad'; calcularVenta(); });
    campos.costoMoneda.addEventListener('change', () => { lastModified = 'utilidad'; calcularVenta(); });
    campos.utilidad.addEventListener('input', () => { lastModified = 'utilidad'; calcularVenta(); });
    campos.ventaMonto.addEventListener('input', () => { lastModified = 'venta'; calcularUtilidad(); });
    campos.ventaMoneda.addEventListener('change', () => { lastModified = 'utilidad'; calcularVenta(); });
    campos.impuesto.addEventListener('change', actualizarPrecioFinal); // <<< NUEVO: Actualiza el precio final si cambia el impuesto

    // Inicialización
    if (campos.ventaMonto.value) {
        actualizarPrecioFinal();
    }
});