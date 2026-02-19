/* static/admin/js/orden_pago_admin.js */

(function($) {
    $(document).ready(function() {

        function toggleFields(row) {
            // Buscamos el select de "Tipo" en la fila actual
            var selectTipo = row.find('select[id$="-tipo"]');
            if (selectTipo.length === 0) return;

            // Obtenemos el texto de la opción seleccionada (ej: "Cheque Propio", "Efectivo")
            var tipoText = selectTipo.find('option:selected').text().toLowerCase();

            // Campos a controlar
            var fieldChequeTercero = row.find('.field-cheque_tercero');
            var fieldPropioNro = row.find('.field-cheque_propio_nro');
            var fieldEsEcheq = row.find('.field-es_echeq');
            var fieldFechaPago = row.find('.field-fecha_pago_cheque');
            # var fieldBanco = row.find('.field-banco_origen'); // Si lo usas en el inline

            // Lógica de visualización
            if (tipoText.includes('propio')) {
                // Es Cheque Propio
                fieldChequeTercero.hide();
                fieldPropioNro.show();
                fieldEsEcheq.show();
                fieldFechaPago.show();
                // fieldBanco.show();
            } else if (tipoText.includes('tercero') || tipoText.includes('cartera')) {
                // Es Cheque de Tercero
                fieldChequeTercero.show();
                fieldPropioNro.hide();
                fieldEsEcheq.hide();
                fieldFechaPago.hide();
                // fieldBanco.hide();
            } else {
                // Efectivo, Transferencia, etc.
                fieldChequeTercero.hide();
                fieldPropioNro.hide();
                fieldEsEcheq.hide();
                fieldFechaPago.hide();
                // fieldBanco.hide();
            }
        }

        // 1. Ejecutar al cargar la página para las filas existentes
        $('tr[id^="valores-"]').each(function() {
            toggleFields($(this));
        });

        // 2. Escuchar cambios en el select de "Tipo"
        $(document).on('change', 'select[id$="-tipo"]', function() {
            var row = $(this).closest('tr');
            toggleFields(row);
        });

        // 3. Compatibilidad con "Add another" (nuevas filas dinámicas)
        $(document).on('formset:added', function(event, row) {
            toggleFields($(row));
        });
    });
})(django.jQuery);