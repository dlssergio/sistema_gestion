// static/admin/js/articulo_admin.js
window.addEventListener('DOMContentLoaded', (event) => {
    const cotizacionesElement = document.getElementById('cotizaciones-json');
    const tasasImpuestosElement = document.getElementById('tasas-impuestos-json');

    if (!cotizacionesElement || !tasasImpuestosElement) { return; }

    const cotizaciones = JSON.parse(cotizacionesElement.textContent);
    const reglasImpuesto = JSON.parse(tasasImpuestosElement.textContent);

    const campos = {
        costoMonto: document.querySelector('#id_precio_costo_monto'),
        costoMoneda: document.querySelector('#id_precio_costo_moneda'),
        utilidad: document.querySelector('#id_utilidad'),
        ventaMonto: document.querySelector('#id_precio_venta_monto'),
        ventaMoneda: document.querySelector('#id_precio_venta_moneda'),
        impuestos: document.querySelector('#id_impuestos'),
        precioFinal: document.querySelector('.field-precio_final_form .readonly'),
    };

    let lastModified = null;

    function getCotizacion(idMoneda) {
        return parseFloat(cotizaciones[idMoneda]) || 1.0;
    }

    function calcularVenta() {
        if (lastModified === 'venta') return;

        const valCosto = parseFloat(campos.costoMonto?.value) || 0;
        const valUtilidad = parseFloat(campos.utilidad?.value) || 0;

        const cotizCosto = getCotizacion(campos.costoMoneda?.value);
        const cotizVenta = getCotizacion(campos.ventaMoneda?.value);

        const costoBase = valCosto * cotizCosto;
        const ventaBase = costoBase * (1 + (valUtilidad / 100));

        if (cotizVenta > 0 && campos.ventaMonto) {
            // CORRECCIÓN CRÍTICA: toFixed(2) para cumplir con el modelo de base de datos
            campos.ventaMonto.value = (ventaBase / cotizVenta).toFixed(2);
        }

        actualizarPrecioFinal();
    }

    function calcularUtilidad() {
        if (lastModified === 'utilidad') return;

        const valCosto = parseFloat(campos.costoMonto?.value) || 0;
        const valVenta = parseFloat(campos.ventaMonto?.value) || 0;

        const cotizCosto = getCotizacion(campos.costoMoneda?.value);
        const cotizVenta = getCotizacion(campos.ventaMoneda?.value);

        const costoBase = valCosto * cotizCosto;
        const ventaBase = valVenta * cotizVenta;

        if (costoBase > 0 && campos.utilidad) {
            const nuevaUtilidad = ((ventaBase / costoBase) - 1) * 100;
            campos.utilidad.value = nuevaUtilidad.toFixed(2);
        }

        actualizarPrecioFinal();
    }

    function actualizarPrecioFinal() {
        if (!campos.precioFinal) return;

        const valVenta = parseFloat(campos.ventaMonto?.value) || 0;
        let totalConImpuestos = valVenta;

        if (campos.impuestos) {
            const opcionesSeleccionadas = Array.from(campos.impuestos.selectedOptions).map(opt => parseInt(opt.value));
            opcionesSeleccionadas.forEach(idImpuesto => {
                const regla = reglasImpuesto.find(r => r.id === idImpuesto);
                if (regla) {
                    const tasa = parseFloat(regla.tasa);
                    totalConImpuestos += valVenta * (tasa / 100);
                }
            });
        }

        const simbolo = campos.ventaMoneda?.options[campos.ventaMoneda.selectedIndex]?.text.split('-')[0].trim() || '$';
        campos.precioFinal.textContent = `${simbolo} ${totalConImpuestos.toLocaleString('es-AR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    }

    // Event Listeners
    if (campos.costoMonto) campos.costoMonto.addEventListener('input', () => { lastModified = 'utilidad'; calcularVenta(); });
    if (campos.costoMoneda) campos.costoMoneda.addEventListener('change', () => { lastModified = 'utilidad'; calcularVenta(); });
    if (campos.utilidad) campos.utilidad.addEventListener('input', () => { lastModified = 'utilidad'; calcularVenta(); });
    if (campos.ventaMonto) campos.ventaMonto.addEventListener('input', () => { lastModified = 'venta'; calcularUtilidad(); });
    if (campos.ventaMoneda) campos.ventaMoneda.addEventListener('change', () => { lastModified = 'utilidad'; calcularVenta(); });
    if (campos.impuestos) campos.impuestos.addEventListener('change', actualizarPrecioFinal);

    if (campos.ventaMonto && campos.ventaMonto.value) { actualizarPrecioFinal(); }
});