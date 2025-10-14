// static/admin/js/compras_admin.js

if (window.django && window.django.jQuery) {
    const $ = django.jQuery;

    // <<< CRÍTICO: Función que reescribe la URL de la Lupa (RawId Hack) >>>
    function updateRawIdLookupLinks(proveedorId) {
        const $lookups = $('#items-group').find('.related-widget-wrapper a.related-lookup');

        // Filtro estricto que Django entiende: ?proveedor__id__exact=X
        const filterParam = proveedorId ? `?proveedor__id__exact=${proveedorId}` : '';

        $lookups.each(function() {
            const $link = $(this);
            let href = $link.attr('href').split('?')[0]; // Toma solo la URL base

            // Reconstruye el href con el nuevo parámetro de filtro.
            $link.attr('href', href + filterParam);
        });
    }

    // <<< CRÍTICO: Función para Habilitar/Deshabilitar Campos del Inline >>>
    function toggleInlineFields(disable) {
        const inlineContainer = $('#items-group');
        if (!inlineContainer.length) return;

        // CRÍTICO: Apuntamos a los inputs de RawIdWidget
        const $articuloInputs = inlineContainer.find('input[name$="-articulo"]');
        const $costoInputs = inlineContainer.find('input[name$="-precio_costo_unitario_0"]');
        const $monedaSelects = inlineContainer.find('select[name$="-precio_costo_unitario_1"]');
        const $cantidadInputs = inlineContainer.find('input[name$="-cantidad"]');

        // El botón de la lupa y el campo de visualización (lectura)
        const $searchIcons = inlineContainer.find('.related-widget-wrapper a.related-lookup');
        const $visualInputs = inlineContainer.find('input.vForeignKeyRawIdAdminField');

        if (disable) {
            $articuloInputs.prop('disabled', true);
            $costoInputs.prop('disabled', true);
            $monedaSelects.prop('disabled', true);
            $cantidadInputs.prop('disabled', true);
            $searchIcons.hide(); // Ocultar el botón de la lupa
            $visualInputs.prop('disabled', true);
        } else {
            $articuloInputs.prop('disabled', false);
            $costoInputs.prop('disabled', false);
            $monedaSelects.prop('disabled', false);
            $cantidadInputs.prop('disabled', false);
            $searchIcons.show(); // Mostrar el botón de la lupa
            $visualInputs.prop('disabled', false);
        }
    }

    // --- Lógica del Comprobante de Compra (Actualización de Totales y Precio Avanzado) ---
    $(document).ready(function() {
        console.log("Faro ERP (Diagnóstico v2): Script INICIADO.");

        const inlineContainer = $('#items-group');
        const csrfToken = $('input[name="csrfmiddlewaretoken"]').val();

        // --- Función para actualizar Subtotal y Total (se mantiene) ---
        function actualizarCalculos() {
            // ... (Tu código de actualizarCalculos se mantiene igual) ...
            console.log("Faro ERP (Diagnóstico v2): --- Iniciando actualizarCalculos ---");
            const itemsData = [];
            if (!inlineContainer.length) return;

            inlineContainer.find('tbody tr.dynamic-items').not('.empty-form').each(function(index) {
                const row = $(this);
                // CRÍTICO: Ahora se lee el valor del INPUT RawId
                const articuloId = row.find('input[name$="-articulo"]').val();
                const cantidad = row.find('input[name$="-cantidad"]').val() || '0';
                const precioMonto = row.find('input[name$="-precio_costo_unitario_0"]').val() || '0';
                const precioMonedaId = row.find('select[name$="-precio_costo_unitario_1"]').val();

                console.log(`Faro ERP (Diagnóstico v2): Fila #${index} | ArticuloID: ${articuloId} | Cant: ${cantidad} | Precio: ${precioMonto} | MonedaID: ${precioMonedaId}`);

                if (articuloId) {
                    itemsData.push({
                        articulo: articuloId,
                        cantidad: cantidad,
                        precio_monto: precioMonto,
                        precio_moneda_id: precioMonedaId,
                    });
                }
            });

            console.log("Faro ERP (Diagnóstico v2): Datos recolectados para enviar a la API:", JSON.stringify(itemsData));
            const url = `/admin/compras/comprobantecompra/api/calcular-totales/`;
            console.log("Faro ERP (Diagnóstico v2): Realizando fetch a:", url);

            fetch(url, {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken}, // Usar la variable global
                body: JSON.stringify({ items: itemsData, tipo_comprobante: $('#id_tipo_comprobante').val() })
            })
            .then(response => {
                console.log("Faro ERP (Diagnóstico v2): Respuesta recibida del servidor. Estado:", response.status);
                if (!response.ok) {
                    console.error("Faro ERP (Diagnóstico v2): La respuesta del servidor NO fue OK.");
                    response.text().then(text => {
                        console.error("Faro ERP (Diagnóstico v2): Cuerpo de la respuesta de error:", text);
                    });
                    return Promise.reject(new Error(`Respuesta del servidor: ${response.status}`));
                }
                return response.json();
            })
            .then(data => {
                console.log("Faro ERP (Diagnóstico v2): Datos JSON procesados:", data);
                if (data.error) {
                    console.error("Faro ERP (Diagnóstico v2): El backend devolvió un error de negocio:", data.error);
                    return;
                }

                const currency = data.currency_symbol || '$';
                $('div.field-subtotal div.readonly').text(`${currency} ${data.subtotal}`);
                $('div.field-total div.readonly').text(`${currency} ${data.total}`);
                let impuestosHtml = '<ul>';
                for (const [nombre, monto] of Object.entries(data.impuestos)) {
                    impuestosHtml += `<li><strong>${nombre}:</strong> ${currency} ${monto}</li>`;
                }
                impuestosHtml += '</ul>';
                $('div.field-impuestos_desglosados div.readonly').html(impuestosHtml);
                console.log("Faro ERP (Diagnóstico v2): Campos de totales actualizados en la UI.");
            })
            .catch(error => {
                console.error("Faro ERP (Diagnóstico v2): Error CRÍTICO en la llamada fetch o al procesar la respuesta:", error);
            });
        }

        // --- Función CRÍTICA: Obtiene el precio avanzado del proveedor ---
        async function handleArticuloChange(selectElement) {
            // CRÍTICO: El RawIdWidget dispara el evento change en el INPUT
            const $articuloInput = $(selectElement);
            const articuloId = $articuloInput.val();
            const row = $articuloInput.closest('tr.dynamic-items');

            // CRÍTICO: Obtenemos el proveedor del formulario principal
            const proveedorId = $('#id_proveedor').val();

            // Elementos de la fila
            const cantidadInput = row.find('input[name$="-cantidad"]');
            const costoMontoInput = row.find('input[name$="-precio_costo_unitario_0"]');
            const costoMonedaSelect = row.find('select[name$="-precio_costo_unitario_1"]');

            // 1. Validación y limpieza
            if (!articuloId) {
                row.find('input[name$="-cantidad"]').val('0');
                costoMontoInput.val('0.00');
                actualizarCalculos();
                return;
            }

            // 2. Si el proveedor no está seleccionado, no podemos hacer NADA (validación de negocio estricta)
            if (!proveedorId) {
                console.error("Faro ERP: Proveedor no seleccionado. La lógica de negocio requiere un proveedor para obtener precios.");
                actualizarCalculos();
                return;
            }

            try {
                // 3. Llamada a la nueva API avanzada
                const url = `/admin/compras/comprobantecompra/get-precio-proveedor/${proveedorId}/${articuloId}/`;
                console.log("Faro ERP: Buscando precio avanzado en:", url);

                const response = await fetch(url);
                const data = await response.json();

                if (!response.ok) {
                    if (response.status === 404 && data.error === 'VALIDACION_PRECIO') {
                         console.error("Faro ERP: VALIDACIÓN: Artículo NO encontrado en lista de precios activa del proveedor.");
                         alert(`ERROR: ${data.message} - Debe seleccionar un proveedor con una lista de precios activa.`);
                    } else {
                         console.error("Faro ERP: Error al obtener precio avanzado o error de servidor:", data.message);
                    }
                    // Si falla la lógica (sin precio), se queda en 0.00
                    costoMontoInput.val('0.00');
                    actualizarCalculos();
                    return;
                }

                // 4. Poblar campos
                costoMontoInput.val(data.amount);
                if (data.currency_id) {
                    costoMonedaSelect.val(data.currency_id).trigger('change');
                }
                if (!cantidadInput.val()) {
                    cantidadInput.val('1'); // Valor por defecto
                }

                console.log(`Faro ERP: Precio efectivo autocompletado: ${data.amount}. Fuente: ${data.source}`);

            } catch (error) {
                console.error('Faro ERP: Error CRÍTICO en la llamada fetch del precio avanzado:', error);
                costoMontoInput.val('0.00');
            }

            // 5. Actualizar totales después de la carga del precio
            actualizarCalculos();
        }

        // <<< CRÍTICO: Estado Inicial y Listener de Proveedor >>>
        if (inlineContainer.length) {

            // Estado inicial: Deshabilita si no hay proveedor al cargar
            const initialProveedorId = $('#id_proveedor').val();
            toggleInlineFields(initialProveedorId === '');
            // CRÍTICO: Actualizar los enlaces de la Lupa en el estado inicial
            updateRawIdLookupLinks(initialProveedorId);

            // 🛑 CRÍTICO: Escuchar el evento 'change' del INPUT RawId
            inlineContainer.on('change', 'input[name$="-articulo"]', function (e) { handleArticuloChange(this); });

            // Listener para el Proveedor: Habilitar/Deshabilitar campos del inline
            $('#id_proveedor').on('change', function() {
                const proveedorSeleccionado = $(this).val();
                const shouldDisable = proveedorSeleccionado === '';

                // 1. Habilitar/Deshabilitar los campos del inline
                toggleInlineFields(shouldDisable); // Si es vacío, debe deshabilitarse.

                // 2. CRÍTICO: ACTUALIZAR LOS ENLACES DE LA LUPA
                updateRawIdLookupLinks(proveedorSeleccionado);

                // 3. Forzar la revalidación de precios si se seleccionó un proveedor
                if (proveedorSeleccionado) {
                    console.log("Faro ERP: Cambio de Proveedor detectado. Revalidando precios de ítems.");
                    inlineContainer.find('input[name$="-articulo"]').each(function() {
                        // Forzamos la re-ejecución de la lógica de cambio de artículo para la fila
                        handleArticuloChange(this);
                    });
                } else {
                     // Si el proveedor se limpió, deshabilita y limpia los precios
                     inlineContainer.find('input[name$="-precio_costo_unitario_0"]').val('0.00');
                     actualizarCalculos();
                }
            });

            // CRÍTICO: Al agregar una nueva fila, debemos actualizar también el enlace de esa nueva lupa
            $(document).on('formset:added', function(event, $row, formsetName) {
                if (formsetName === 'comprobantecompraitem_set') {
                    const currentProveedorId = $('#id_proveedor').val();
                    updateRawIdLookupLinks(currentProveedorId);
                }
            });

            // Al cambiar cantidad, precio o tipo de comprobante (para totalizar)
            inlineContainer.on('input', 'input[name$="-cantidad"], input[name$="-precio_costo_unitario_0"]', actualizarCalculos);
            inlineContainer.on('change', 'select[name$="-precio_costo_unitario_1"], #id_tipo_comprobante', actualizarCalculos);
        }
    });


    // --- LÓGICA ESPECÍFICA: Actualización del Costo Unitario Efectivo en la Lista de Precios ---

    // ... (Tu código para la Lista de Precios se mantiene igual) ...

    $(document).ready(function() {
        const listaPreciosInlineContainer = $('#itemlistapreciosproveedor_set-group');

        // CRÍTICO: Función que llama a la API para obtener el cálculo real (sólo si la fila tiene PK/ID)
        async function actualizarCostoEfectivoInline(row) {
            // El ID del ítem de la lista se encuentra en un campo oculto
            const itemPk = row.find('input[name$="-id"]').val();
            const $effectiveCostDisplay = row.find('div.field-costo_unitario_efectivo div.readonly');

            // 1. Si el ítem es nuevo o no tiene PK, no podemos llamar al API.
            if (!itemPk) {
                $effectiveCostDisplay.text('Guardar para calcular CUE');
                return;
            }

            try {
                // 2. Llamada a la nueva API
                const url = `/admin/compras/listapreciosproveedor/get-costo-efectivo-lista/${itemPk}/`;
                const response = await fetch(url);
                const data = await response.json();

                if (!response.ok) {
                    $effectiveCostDisplay.text('Error de cálculo');
                    return;
                }

                // 3. Actualizar el campo de solo lectura
                $effectiveCostDisplay.text(`${data.amount} ${data.currency_code}/Stock`);

            } catch (error) {
                console.error('Faro ERP: Error al obtener el costo efectivo de lista:', error);
                $effectiveCostDisplay.text('Error de conexión');
            }
        }

        if (listaPreciosInlineContainer.length) {
            console.log("Faro ERP: Activando listeners para Lista de Precios de Proveedor.");

            // Eventos para notificar que el valor DEBE ser recalculado
            listaPreciosInlineContainer.on('input change', 'input[name$="-precio_costo_0"], input[name$="-bonificacion_porcentaje"], input[name$="-cantidad_minima"], select[name$="-unidad_medida_compra"], select[name$="-precio_costo_1"]', function() {
                // Notificar al usuario que debe guardar para ver el cambio
                $(this).closest('tr').find('div.field-costo_unitario_efectivo div.readonly').text('Guardar para actualizar');
            });

            // Forzar el cálculo al cargar la página (para las filas ya guardadas)
            listaPreciosInlineContainer.find('tbody tr.dynamic-itemlistapreciosproveedor').not('.empty-form').each(function() {
                 actualizarCostoEfectivoInline($(this));
            });

            // Al añadir una nueva fila vacía (inicializa el mensaje)
            $(document).on('click', '.add-row a', function() {
                 setTimeout(function() {
                    listaPreciosInlineContainer.find('tbody tr.dynamic-itemlistapreciosproveedor').not('.empty-form').last().each(function() {
                        // El cálculo real ocurrirá cuando se guarde la lista y se recargue la página.
                        $(this).find('div.field-costo_unitario_efectivo div.readonly').text('Guardar para calcular CUE');
                    });
                 }, 50);
            });
        }
    });

}