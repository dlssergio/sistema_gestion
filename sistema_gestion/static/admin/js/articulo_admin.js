// static/admin/js/articulo_admin.js (VERSIÓN FINAL CON IDs CONSISTENTES)

(function($) {
    $(document).ready(function() {
        const cotizacionesElement = document.getElementById('cotizaciones-json');
        const tasasImpuestosElement = document.getElementById('tasas-impuestos-json');
        if (!cotizacionesElement || !tasasImpuestosElement) { return; }

        const cotizaciones = JSON.parse(cotizacionesElement.textContent);
        const reglasImpuesto = JSON.parse(tasasImpuestosElement.textContent);

        const campos = {
            costoMonto: $('#id_precio_costo_monto'),
            costoMoneda: $('#id_precio_costo_moneda'),
            utilidad: $('#id_utilidad'),
            // <<< SE ACTUALIZAN LOS SELECTORES DE VENTA >>>
            ventaMonto: $('#id_precio_venta_monto'),
            ventaMoneda: $('#id_precio_venta_moneda'),
            impuesto: $('#id_impuesto'),
            precioFinal: $('.field-precio_final_form .readonly'),
        };

        for (const key in campos) {
            if (campos[key].length === 0) {
                console.error(`Faro ERP (Error): No se encontró el campo del formulario: ${key}`);
                return;
            }
        }

        let lastModified = null;

        function calcularVenta() {
            if (lastModified === 'venta') return;
            const cotizacionCosto = parseFloat(cotizaciones[campos.costoMoneda.val()]) || 1;
            const costoMonto = parseFloat(campos.costoMonto.val()) || 0;
            const utilidad = parseFloat(campos.utilidad.val()) || 0;

            campos.ventaMoneda.val(campos.costoMoneda.val());
            const cotizacionVenta = parseFloat(cotizaciones[campos.ventaMoneda.val()]) || 1;

            const costoEnBase = costoMonto * cotizacionCosto;
            const ventaEnBase = costoEnBase * (1 + (utilidad / 100));

            if (cotizacionVenta > 0) {
                campos.ventaMonto.val((ventaEnBase / cotizacionVenta).toFixed(2));
            }
            actualizarPrecioFinal();
        }

        function calcularUtilidad() {
            if (lastModified === 'utilidad') return;
            const cotizacionCosto = parseFloat(cotizaciones[campos.costoMoneda.val()]) || 1;
            const costoMonto = parseFloat(campos.costoMonto.val()) || 0;
            const cotizacionVenta = parseFloat(cotizaciones[campos.ventaMoneda.val()]) || 1;
            const ventaMonto = parseFloat(campos.ventaMonto.val()) || 0;

            const costoEnBase = costoMonto * cotizacionCosto;
            const ventaEnBase = ventaMonto * cotizacionVenta;

            if (costoEnBase > 0) {
                campos.utilidad.val((((ventaEnBase / costoEnBase) - 1) * 100).toFixed(2));
            } else {
                campos.utilidad.val((0).toFixed(2));
            }
            actualizarPrecioFinal();
        }

        function actualizarPrecioFinal() {
            const ventaMonto = parseFloat(campos.ventaMonto.val()) || 0;
            let totalConImpuestos = ventaMonto;

            const impuestoSeleccionadoId = campos.impuesto.val();
            if (impuestoSeleccionadoId) {
                const regla = reglasImpuesto.find(r => r.id == impuestoSeleccionadoId);
                if (regla) {
                    const tasa = parseFloat(regla.tasa);
                    totalConImpuestos = ventaMonto * (1 + (tasa / 100));
                }
            }
            campos.precioFinal.text(`$${totalConImpuestos.toLocaleString('es-AR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`);
        }

        campos.costoMonto.on('input', () => { lastModified = 'utilidad'; calcularVenta(); });
        campos.costoMoneda.on('change', () => { lastModified = 'utilidad'; calcularVenta(); });
        campos.utilidad.on('input', () => { lastModified = 'utilidad'; calcularVenta(); });
        campos.ventaMonto.on('input', () => { lastModified = 'venta'; calcularUtilidad(); });
        campos.ventaMoneda.on('change', () => { lastModified = 'utilidad'; calcularVenta(); });
        campos.impuesto.on('change', actualizarPrecioFinal);

        calcularVenta();
    });
})(django.jQuery);