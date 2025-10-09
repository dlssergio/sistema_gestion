// en static/admin/js/entidad_form.js (Versión Corregida)
window.addEventListener('DOMContentLoaded', (event) => {
    const sexoSelect = document.querySelector('#id_sexo');
    const dniInput = document.querySelector('#id_dni');
    const cuitInput = document.querySelector('#id_cuit');

    if (!sexoSelect || !dniInput || !cuitInput) { return; }

    function calcularDigitoVerificador(cuit_sin_verificador) {
        const base = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2];
        let suma = 0;
        for (let i = 0; i < base.length; i++) {
            suma += parseInt(cuit_sin_verificador[i]) * base[i];
        }
        let resto = suma % 11;
        let digito = 11 - resto;
        if (digito === 11) { digito = 0; }
        return digito;
    }

    function generarYActualizarCUIL() {
        const dni = dniInput.value;
        const sexo = sexoSelect.value;
        if ((sexo === 'M' || sexo === 'F') && dni.length === 8) {
            let prefijo = (sexo === 'M') ? '20' : '27';
            let digito = calcularDigitoVerificador(prefijo + dni);
            if (digito === 10) {
                prefijo = '23';
                digito = calcularDigitoVerificador(prefijo + dni);
            }
            cuitInput.value = `${prefijo}${dni}${digito}`;
        }
    }

    function extraerDNIdeCUIL() {
        const cuit = cuitInput.value.replace(/-/g, '');
        const prefijo = cuit.substring(0, 2);
        if (cuit.length === 11 && ['20', '23', '27'].includes(prefijo)) {
            dniInput.value = cuit.substring(2, 10);
        }
    }

    dniInput.addEventListener('input', generarYActualizarCUIL);
    sexoSelect.addEventListener('change', generarYActualizarCUIL);
    cuitInput.addEventListener('input', extraerDNIdeCUIL);
});