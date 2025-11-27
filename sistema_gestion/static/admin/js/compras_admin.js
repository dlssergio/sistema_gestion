/* static/admin/js/compras_admin.js - VERSIÓN FINAL (HARD RESET) */
'use strict';

window.addEventListener('DOMContentLoaded', function() {
    if (!window.django || !window.django.jQuery) return;
    const $ = django.jQuery;
    const inlineGroup = $('#items-group');

    if (!inlineGroup.length) return;

    console.log("🚀 Faro ERP: Compras Admin Script (Hard Reset)");

    // 1. CONFIGURACIÓN DEL SELECTOR (VALORES FIJOS)
    // No leemos del DOM para evitar errores en clones. Escribimos a fuego.
    function initSelect2($element) {
        // Destruir instancia previa si existe
        if ($element.hasClass("select2-hidden-accessible")) {
            try { $element.select2('destroy'); } catch(e) {}
        }

        // Limpiar basura del clonado
        $element.removeAttr('data-select2-id');
        $element.removeAttr('tabindex');
        $element.removeAttr('aria-hidden');
        $element.removeClass('select2-hidden-accessible admin-autocomplete'); // Quitamos clase Django

        // Borrar contenedor visual residual
        $element.next('.select2-container').remove();
        $element.show();

        // Inicializar con NUESTRA configuración
        $element.select2({
            ajax: {
                url: '/admin/autocomplete/',
                dataType: 'json',
                delay: 250,
                data: function(params) {
                    return {
                        term: params.term || '',
                        page: params.page,
                        // DATOS FIJOS (Corregir si tu app se llama diferente en settings)
                        app_label: 'compras',
                        model_name: 'comprobantecompraitem',
                        field_name: 'articulo',
                        // FILTRO CRÍTICO
                        proveedor_id: $('#id_proveedor').val()
                    };
                }
            },
            minimumInputLength: 0,
            placeholder: 'Seleccione un artículo',
            allowClear: true,
            width: '100%'
        });
        console.log("✅ Select2 Reiniciado en:", $element.attr('name'));
    }

    // 2. INICIALIZACIÓN (Filas existentes)
    inlineGroup.find('tr.dynamic-items select[name$="-articulo"]').each(function() {
        initSelect2($(this));
    });

    // 3. INTERCEPTOR DE NUEVAS FILAS
    $(document).on('formset:added', function(event, $row, formsetName) {
        if (formsetName === 'items') {
            console.log("⚡ Nueva fila. Esperando...");

            // Esperamos 200ms a que el DOM se calme
            setTimeout(function() {
                const $select = $row.find('select[name$="-articulo"]');

                // Limpiar valores heredados del clon
                $select.val(null);
                $row.find('input[name$="-cantidad"]').val(1); // Cantidad 1 por defecto
                $row.find('input[name$="-precio_costo_unitario_0"]').val('');

                // Aplicar configuración
                initSelect2($select);
            }, 200);
        }
    });

    // 4. LÓGICA DE PRECIO Y CANTIDAD
    // Usamos delegación global 'body' para asegurar que agarre elementos nuevos
    $('body').on('select2:select', 'select[name$="-articulo"]', async function(e) {
        const $select = $(this);

        // Verificar que sea del inline de compras
        if (!$select.closest('#items-group').length) return;

        const row = $select.closest('tr');
        const articuloId = $select.val();
        const proveedorId = $('#id_proveedor').val();

        const precioInput = row.find('input[name$="-precio_costo_unitario_0"]');
        const cantidadInput = row.find('input[name$="-cantidad"]');

        console.log("🔎 Buscando precio para:", articuloId);

        if (!articuloId) return;

        try {
            const url = `/admin/compras/comprobantecompra/get-precio-proveedor/${proveedorId}/${articuloId}/`;
            const res = await fetch(url);
            if (res.ok) {
                const data = await res.json();

                // Seteamos Precio
                precioInput.val(data.amount);

                // Seteamos Cantidad (Validación)
                let cant = cantidadInput.val();
                if (!cant || cant == 0 || cant == '0') {
                    cantidadInput.val(1);
                }

                // Efecto visual
                precioInput.css({'background-color': '#d4edda', 'transition':'0.5s'});
                setTimeout(()=>precioInput.css('background-color',''), 500);
            }
        } catch (e) { console.error(e); }
        finally { actualizarCalculos(); }
    });

    // 5. CAMBIO DE PROVEEDOR
    $('#id_proveedor').on('change', function() {
        // Resetear selects visualmente
        inlineGroup.find('tr.dynamic-items:not(.empty-form) select[name$="-articulo"]').val(null).trigger('change');
        actualizarCalculos();
    });

    // 6. CÁLCULOS (Sin cambios)
    function actualizarCalculos() {
        const itemsData = [];
        inlineGroup.find('tr.dynamic-items:not(.empty-form)').each(function() {
            const row = $(this);
            if (row.find('.action-checkbox input').is(':checked')) return;

            const articuloId = row.find('select[name$="-articulo"]').val();
            if (articuloId) {
                itemsData.push({
                    articulo: articuloId,
                    cantidad: row.find('input[name$="-cantidad"]').val() || '0',
                    precio_monto: row.find('input[name$="-precio_costo_unitario_0"]').val() || '0',
                    precio_moneda_id: row.find('select[name$="-precio_costo_unitario_1"]').val()
                });
            }
        });

        fetch(`/admin/compras/comprobantecompra/api/calcular-totales/`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': $('input[name="csrfmiddlewaretoken"]').val()},
            body: JSON.stringify({
                items: itemsData,
                tipo_comprobante: $('#id_tipo_comprobante').val(),
                proveedor: $('#id_proveedor').val()
            })
        })
        .then(res => res.json())
        .then(data => {
            if (data.error) return;
            $('.field-subtotal .readonly').text(`${data.currency_symbol} ${data.subtotal}`);
            $('.field-total .readonly').text(`${data.currency_symbol} ${data.total}`);

            let html = '<ul style="margin:0; padding-left:15px;">';
            for (const [k, v] of Object.entries(data.impuestos)) html += `<li><strong>${k}:</strong> ${data.currency_symbol} ${v}</li>`;
            html += '</ul>';
            if (Object.keys(data.impuestos).length===0) html="N/A";
            $('.field-impuestos_desglosados .readonly').html(html);
        });
    }

    $(document).on('input change', 'input[name$="-cantidad"], input[name$="-precio_costo_unitario_0"]', function() {
        setTimeout(actualizarCalculos, 100);
    });

    setTimeout(actualizarCalculos, 500);
});