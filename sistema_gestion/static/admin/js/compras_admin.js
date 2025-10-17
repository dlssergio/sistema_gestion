// static/admin/js/compras_admin.js (VERSIÓN DEFINITIVA Y ROBUSTA)

window.addEventListener('DOMContentLoaded', (event) => {
    if (!(window.django && window.django.jQuery)) {
        return;
    }

    const $ = django.jQuery;
    const inlineGroup = $('#items-group');
    if (!inlineGroup.length) return;

    // --- LÓGICA PRINCIPAL ---

    function initializeRow(row) {
        const $row = $(row);
        const $select = $row.find('select[name$="-articulo"]');

        if ($select.data('select2')) {
            $select.select2('destroy');
        }

        $select.select2({
            ajax: {
                data: function(params) {
                    return {
                        term: params.term,
                        page: params.page,
                        proveedor_id: $('#id_proveedor').val()
                    };
                }
            }
        });
    }

    function toggleInlineFields(disable) {
        const fields = 'input[name$="-cantidad"], input[name$="-precio_costo_unitario_0"], select[name$="-precio_costo_unitario_1"]';
        inlineGroup.find(fields).prop('disabled', disable);
        inlineGroup.find('span.select2-selection').css('pointer-events', disable ? 'none' : 'auto').css('background-color', disable ? '#eee' : '#fff');
    }

    async function handleArticuloChange(selectElement) {
        const $select = $(selectElement);
        const row = $select.closest('tr.dynamic-items');
        const articuloId = $select.val();
        const proveedorId = $('#id_proveedor').val();

        const costoMontoInput = row.find('input[name$="-precio_costo_unitario_0"]');
        const costoMonedaSelect = row.find('select[name$="-precio_costo_unitario_1"]');
        const cantidadInput = row.find('input[name$="-cantidad"]');

        if (!articuloId || !proveedorId) {
            costoMontoInput.val('0.0000');
            actualizarCalculos();
            return;
        }

        try {
            const url = `/admin/compras/comprobantecompra/get-precio-proveedor/${proveedorId}/${articuloId}/`;
            const response = await fetch(url);

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ message: 'Respuesta inválida del servidor.' }));
                throw new Error(errorData.message || 'Precio no encontrado para este proveedor.');
            }

            const data = await response.json();
            costoMontoInput.val(data.amount);
            if (data.currency_id) {
                costoMonedaSelect.val(data.currency_id).trigger('change');
            }
            if (!cantidadInput.val() || parseFloat(cantidadInput.val()) === 0) {
                cantidadInput.val('1');
            }
        } catch (error) {
            console.error('Faro ERP (Error Precio):', error.message);
            alert(`No se pudo obtener el precio. Razón: ${error.message}`);
            costoMontoInput.val('0.0000');
        } finally {
            actualizarCalculos();
        }
    }

    function actualizarCalculos() {
        let subtotalTotal = 0;
        let monedaSimbolo = '$';

        inlineGroup.find('tr.dynamic-items:not(.empty-form)').each(function() {
            const row = $(this);
            const cantidad = parseFloat(row.find('input[name$="-cantidad"]').val()) || 0;
            const precio = parseFloat(row.find('input[name$="-precio_costo_unitario_0"]').val()) || 0;
            const monedaSelect = row.find('select[name$="-precio_costo_unitario_1"] option:selected');

            const itemSubtotal = cantidad * precio;

            const subtotalCol = row.find('.field-subtotal');
            if (subtotalCol.length) {
                subtotalCol.text(`${monedaSelect.text().split(' ')[0] || '$'} ${itemSubtotal.toFixed(2)}`);
            }

            subtotalTotal += itemSubtotal;
            if (monedaSelect.length) monedaSimbolo = monedaSelect.text().split(' ')[0];
        });

        const subtotalField = $('.field-subtotal .readonly');
        if (subtotalField.length) {
            subtotalField.text(`${monedaSimbolo} ${subtotalTotal.toFixed(2)}`);
            $('.field-total .readonly').text(`${monedaSimbolo} ${subtotalTotal.toFixed(2)} (sin imp.)`);
        }
    }

    inlineGroup.find('tr.dynamic-items').each(function() {
        initializeRow(this);
    });
    toggleInlineFields(!$('#id_proveedor').val());

    $('#id_proveedor').on('change', function() {
        const proveedorId = $(this).val();

        inlineGroup.find('tr.dynamic-items:not(.empty-form)').each(function() {
             $(this).find('select[name$="-articulo"]').val(null).trigger('change');
        });

        inlineGroup.find('tr.dynamic-items').each(function() {
            initializeRow(this);
        });

        toggleInlineFields(!proveedorId);
        actualizarCalculos();
    });

    $(document).on('formset:added', function(event, $row, formsetName) {
        if (formsetName === 'items') {
            initializeRow($row);
            toggleInlineFields(!$('#id_proveedor').val());
        }
    });

    inlineGroup.on('select2:select', 'select[name$="-articulo"]', function(e) {
        handleArticuloChange(this);
    });

    inlineGroup.on('select2:clear', 'select[name$="-articulo"]', function(e) {
        handleArticuloChange(this);
    });

    inlineGroup.on('input change', 'input[name$="-cantidad"], input[name$="-precio_costo_unitario_0"], select[name$="-precio_costo_unitario_1"]', function() {
        setTimeout(actualizarCalculos, 50);
    });

    if (inlineGroup.find('th.field-subtotal').length === 0) {
        inlineGroup.find('thead tr').append('<th class="field-subtotal">Subtotal</th>');
        inlineGroup.find('tbody tr.dynamic-items').append('<td class="field-subtotal"></td>');
    }
});