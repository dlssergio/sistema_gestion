// static/admin/js/compras_admin.js (VERSIÓN CORREGIDA Y ROBUSTA)

window.addEventListener('DOMContentLoaded', (event) => {
    if (!(window.django && window.django.jQuery)) {
        return;
    }

    const $ = django.jQuery;
    const inlineGroup = $('#items-group');

    // Si no hay grupo de items, salimos (ej: vista lista)
    if (!inlineGroup.length) return;

    console.log("Faro ERP: Compras Admin Script Cargado");

    // --- LÓGICA PRINCIPAL ---

    function initializeRow(row) {
        const $row = $(row);
        const $select = $row.find('select[name$="-articulo"]');

        // Solo intervenimos si es un campo Select2
        if ($select.hasClass('admin-autocomplete')) {

            // 1. Destruir la instancia actual para reconfigurarla
            if ($select.data('select2')) {
                $select.select2('destroy');
            }

            // 2. Leer los metadatos de seguridad de Django (VITAL para evitar el 403)
            const appLabel = $select.data('app-label');
            const modelName = $select.data('model-name');
            const fieldName = $select.data('field-name');

            // 3. Re-inicializar Select2 con nuestros parámetros extra
            $select.select2({
                ajax: {
                    url: '/admin/autocomplete/', // URL estándar de Django
                    dataType: 'json',
                    delay: 250,
                    data: function(params) {
                        return {
                            term: params.term,
                            page: params.page,
                            // Parámetros de seguridad obligatorios
                            app_label: appLabel,
                            model_name: modelName,
                            field_name: fieldName,
                            // Nuestro filtro personalizado
                            proveedor_id: $('#id_proveedor').val()
                        };
                    }
                },
                minimumInputLength: 1, // Evita búsquedas vacías pesadas
                placeholder: 'Seleccione un artículo'
            });
        }
    }

    function toggleInlineFields(disable) {
        // Deshabilitar campos si no hay proveedor seleccionado
        const fields = 'input[name$="-cantidad"], input[name$="-precio_costo_unitario_0"], select[name$="-precio_costo_unitario_1"], select[name$="-articulo"]';

        inlineGroup.find(fields).prop('disabled', disable);

        // Efecto visual en Select2
        const pointerEvents = disable ? 'none' : 'auto';
        const opacity = disable ? '0.6' : '1';
        inlineGroup.find('.select2-container').css({
            'pointer-events': pointerEvents,
            'opacity': opacity
        });
    }

    async function handleArticuloChange(selectElement) {
        const $select = $(selectElement);
        const row = $select.closest('tr.dynamic-items');
        const articuloId = $select.val();
        const proveedorId = $('#id_proveedor').val();

        const costoMontoInput = row.find('input[name$="-precio_costo_unitario_0"]');
        const costoMonedaSelect = row.find('select[name$="-precio_costo_unitario_1"]');
        const cantidadInput = row.find('input[name$="-cantidad"]');

        // Si se borró la selección, limpiar y salir
        if (!articuloId) {
            costoMontoInput.val('0.0000');
            actualizarCalculos();
            return;
        }

        console.log(`Faro ERP: Buscando costo para Articulo ${articuloId} y Proveedor ${proveedorId}`);

        try {
            const url = `/admin/compras/comprobantecompra/get-precio-proveedor/${proveedorId}/${articuloId}/`;
            const response = await fetch(url);

            if (!response.ok) throw new Error('Error de red o servidor');

            const data = await response.json();

            // Llenar campos
            costoMontoInput.val(data.amount);

            if (data.currency_id) {
                costoMonedaSelect.val(data.currency_id).trigger('change');
            }

            // Default cantidad 1 si está vacía
            if (!cantidadInput.val() || parseFloat(cantidadInput.val()) === 0) {
                cantidadInput.val('1');
            }

            // Efecto visual de éxito
            costoMontoInput.css('background-color', '#d4edda');
            setTimeout(() => costoMontoInput.css('background-color', ''), 500);

        } catch (error) {
            console.error('Faro ERP Error:', error);
            // No mostramos alert intrusivo, solo log
        } finally {
            actualizarCalculos();
        }
    }

    function actualizarCalculos() {
        let subtotalTotal = 0;
        let monedaSimbolo = '$';

        inlineGroup.find('tr.dynamic-items:not(.empty-form)').each(function() {
            const row = $(this);
            // Si la fila está marcada para borrar, la ignoramos
            if (row.find('.action-checkbox input').is(':checked')) return;

            const cantidad = parseFloat(row.find('input[name$="-cantidad"]').val()) || 0;
            const precio = parseFloat(row.find('input[name$="-precio_costo_unitario_0"]').val()) || 0;
            const monedaSelect = row.find('select[name$="-precio_costo_unitario_1"] option:selected');

            const itemSubtotal = cantidad * precio;

            // Actualizar celda de subtotal visible
            const subtotalCol = row.find('.field-subtotal'); // Asegúrate de tener una columna con esta clase si quieres ver el subtotal por ítem
            if(subtotalCol.length) {
                 // Nota: Esto requiere que hayas agregado la columna en el HTML o via JS como abajo
                 // subtotalCol.text(itemSubtotal.toFixed(2));
            }

            subtotalTotal += itemSubtotal;
            if (monedaSelect.length) monedaSimbolo = monedaSelect.text().split(' ')[0];
        });

        // Actualizar totales generales
        const subtotalField = $('.field-subtotal .readonly');
        if (subtotalField.length) {
            subtotalField.text(`${monedaSimbolo} ${subtotalTotal.toFixed(2)}`);
            // Nota: El total final con impuestos se calcula en backend, aquí mostramos una estimación
            $('.field-total .readonly').text(`${monedaSimbolo} ${subtotalTotal.toFixed(2)} (aprox)`);
        }
    }

    // --- INICIALIZACIÓN ---

    // 1. Inicializar filas existentes
    inlineGroup.find('tr.dynamic-items').each(function() {
        initializeRow(this);
    });

    // 2. Estado inicial de campos (habilitado/deshabilitado según si hay proveedor)
    toggleInlineFields(!$('#id_proveedor').val());

    // 3. Listener cambio de Proveedor
    $('#id_proveedor').on('change', function() {
        const proveedorId = $(this).val();

        // Limpiar artículos al cambiar proveedor para evitar inconsistencias
        inlineGroup.find('tr.dynamic-items:not(.empty-form)').each(function() {
             const select = $(this).find('select[name$="-articulo"]');
             select.val(null).trigger('change');
        });

        // Reinicializar selects con el nuevo ID de proveedor
        inlineGroup.find('tr.dynamic-items').each(function() {
            initializeRow(this);
        });

        toggleInlineFields(!proveedorId);
        actualizarCalculos();
    });

    // 4. Listener para nuevas filas (Django formset)
    $(document).on('formset:added', function(event, $row, formsetName) {
        if (formsetName === 'items') {
            initializeRow($row);
            toggleInlineFields(!$('#id_proveedor').val());
        }
    });

    // 5. Event Delegation para cambio de artículo (Select2)
    // Usamos el evento de select2
    $(document).on('select2:select', 'select[name$="-articulo"]', function(e) {
        handleArticuloChange(this);
    });

    // 6. Event Delegation para recálculo de totales
    $(document).on('input change', 'input[name$="-cantidad"], input[name$="-precio_costo_unitario_0"], select[name$="-precio_costo_unitario_1"]', function() {
        // Debounce ligero para no saturar
        setTimeout(actualizarCalculos, 50);
    });
});