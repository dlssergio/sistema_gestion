# ventas/forms.py
from django import forms
from django.core.exceptions import ValidationError
from .models import ComprobanteVenta
from finanzas.models import CuentaFondo, TipoValor


class ComprobanteVentaAdminForm(forms.ModelForm):
    # Campos virtuales para Cobro Rápido
    cobro_monto = forms.DecimalField(
        required=False,
        label="Monto a Cobrar",
        max_digits=14, decimal_places=2,
        help_text="Deje en 0 para calcular automático el total."
    )
    cobro_tipo = forms.ModelChoiceField(
        queryset=TipoValor.objects.all(),
        required=False,
        label="Medio de Cobro",
        empty_label="--- Seleccione Medio ---"
    )
    cobro_destino = forms.ModelChoiceField(
        # CORRECCIÓN: Usamos 'activa=True' en lugar de 'estado=ACT'
        queryset=CuentaFondo.objects.filter(activa=True),
        required=False,
        label="Caja / Banco Destino",
        empty_label="--- Seleccione Destino ---"
    )

    class Meta:
        model = ComprobanteVenta
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        condicion = cleaned_data.get('condicion_venta')
        tipo = cleaned_data.get('cobro_tipo')
        destino = cleaned_data.get('cobro_destino')

        # Validación: Si es CONTADO, exigimos medio y destino
        if condicion == ComprobanteVenta.CondicionVenta.CONTADO:
            # Solo validamos si es una creación o edición que confirma la venta
            if cleaned_data.get('estado') == ComprobanteVenta.Estado.CONFIRMADO:
                if not tipo:
                    self.add_error('cobro_tipo', 'Para ventas de CONTADO, debe indicar el Medio de Cobro.')
                if not destino:
                    self.add_error('cobro_destino', 'Para ventas de CONTADO, debe indicar la Caja/Banco de destino.')

        return cleaned_data