// static/admin/js/articulo_admin.js (Versión para Admin por Defecto)

window.addEventListener('DOMContentLoaded', (event) => {
    // --- LÓGICA DE CÁLCULO DE PRECIOS ---
    const cotizacionesElement = document.getElementById('cotizaciones-json');
    const tasasImpuestosElement = document.getElementById('tasas-impuestos-json');
    if (!cotizacionesElement || !tasasImpuestosElement) { return; }

    const cotizaciones = JSON.parse(cotizacionesElement.textContent);
    const tasasImpuestos = JSON.parse(tasasImpuestosElement.textContent);

    const camposPrecios = {
        monedaCosto: document.querySelector('#id_moneda_costo'),
        costoOriginal: document.querySelector('#id_precio_costo_original'),
        utilidad: document.querySelector('#id_utilidad'),
        monedaVenta: document.querySelector('#id_moneda_venta'),
        ventaOriginal: document.querySelector('#id_precio_venta_original'),
        impuesto: document.querySelector('#id_impuesto'),
        costoBase: document.querySelector('.field-precio_costo_base .readonly'),
        ventaBase: document.querySelector('.field-precio_venta_base .readonly'),
        precioFinal: document.querySelector('.field-precio_final_form .readonly'),
    };

    function calcularVenta() {
        const cotizacionCosto = parseFloat(cotizaciones[camposPrecios.monedaCosto.value]) || 1;
        const costoOriginal = parseFloat(camposPrecios.costoOriginal.value) || 0;
        const utilidad = parseFloat(camposPrecios.utilidad.value) || 0;
        const cotizacionVenta = parseFloat(cotizaciones[camposPrecios.monedaVenta.value]) || 1;
        const costoBase = costoOriginal * cotizacionCosto;
        const ventaBase = costoBase * (1 + (utilidad / 100));
        if (cotizacionVenta > 0) {
            const nuevaVentaOriginal = ventaBase / cotizacionVenta;
            camposPrecios.ventaOriginal.value = nuevaVentaOriginal.toFixed(2);
        }
        actualizarCamposSoloLectura();
    }

    function calcularUtilidad() {
        const cotizacionCosto = parseFloat(cotizaciones[camposPrecios.monedaCosto.value]) || 1;
        const costoOriginal = parseFloat(camposPrecios.costoOriginal.value) || 0;
        const cotizacionVenta = parseFloat(cotizaciones[camposPrecios.monedaVenta.value]) || 1;
        const ventaOriginal = parseFloat(camposPrecios.ventaOriginal.value) || 0;
        const costoBase = costoOriginal * cotizacionCosto;
        const ventaBase = ventaOriginal * cotizacionVenta;
        if (costoBase > 0 && ventaBase >= costoBase) {
            const nuevaUtilidad = ((ventaBase / costoBase) - 1) * 100;
            camposPrecios.utilidad.value = nuevaUtilidad.toFixed(2);
        } else {
            camposPrecios.utilidad.value = (0).toFixed(2);
        }
        actualizarCamposSoloLectura();
    }

    function actualizarCamposSoloLectura() {
        const cotizacionCosto = parseFloat(cotizaciones[camposPrecios.monedaCosto.value]) || 1;
        const costoOriginal = parseFloat(camposPrecios.costoOriginal.value) || 0;
        const cotizacionVenta = parseFloat(cotizaciones[camposPrecios.monedaVenta.value]) || 1;
        const ventaOriginal = parseFloat(camposPrecios.ventaOriginal.value) || 0;
        const costoBase = costoOriginal * cotizacionCosto;
        const ventaBase = ventaOriginal * cotizacionVenta;
        const tasaImpuesto = parseFloat(tasasImpuestos[camposPrecios.impuesto.value]) || 0;
        const precioFinal = ventaBase * (1 + (tasaImpuesto / 100));
        camposPrecios.costoBase.textContent = `$${costoBase.toLocaleString('es-AR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        camposPrecios.ventaBase.textContent = `$${ventaBase.toLocaleString('es-AR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        camposPrecios.precioFinal.textContent = `$${precioFinal.toLocaleString('es-AR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    }

    camposPrecios.costoOriginal.addEventListener('input', calcularVenta);
    camposPrecios.utilidad.addEventListener('input', calcularVenta);
    camposPrecios.monedaCosto.addEventListener('change', calcularVenta);
    camposPrecios.monedaVenta.addEventListener('change', calcularVenta);
    camposPrecios.ventaOriginal.addEventListener('input', calcularUtilidad);
    camposPrecios.impuesto.addEventListener('change', actualizarCamposSoloLectura);

    // --- LÓGICA DE VISIBILIDAD DE STOCK ---
    const administraStockCheckbox = document.querySelector('#id_administra_stock');
    const stockFields = [
        document.querySelector('.field-unidad_medida'),
        document.querySelector('.field-stock_actual'),
        document.querySelector('.field-stock_minimo'),
        document.querySelector('.field-stock_maximo'),
        document.querySelector('.field-punto_pedido')
    ];

    function toggleStockFields() {
        if (!administraStockCheckbox) return;
        const isStockManaged = administraStockCheckbox.checked;
        stockFields.forEach(field => {
            if (field) {
                field.style.display = isStockManaged ? 'flex' : 'none'; // 'flex' es el display por defecto en el admin de Django
            }
        });
    }

    if (administraStockCheckbox) {
        administraStockCheckbox.addEventListener('change', toggleStockFields);
        toggleStockFields();
    }

    // Ejecución inicial de cálculos al cargar
    calcularVenta();
});