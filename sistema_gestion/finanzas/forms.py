# finanzas/forms.py

from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from .models import LiquidacionTarjeta, CuponTarjeta


class LiquidacionTarjetaForm(forms.ModelForm):
    # Campo especial para seleccionar múltiples cupones
    cupones_pendientes = forms.ModelMultipleChoiceField(
        queryset=CuponTarjeta.objects.none(),
        required=False,
        widget=FilteredSelectMultiple("Cupones Pendientes", is_stacked=False),
        label="Seleccionar Cupones a Liquidar"
    )

    class Meta:
        model = LiquidacionTarjeta
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            # Si ya existe la liquidación, mostramos:
            # 1. Los cupones pendientes de esa tarjeta.
            # 2. Los cupones que YA fueron asignados a esta liquidación (para que aparezcan seleccionados).
            tarjeta = self.instance.tarjeta
            pendientes = CuponTarjeta.objects.filter(tarjeta=tarjeta, estado=CuponTarjeta.Estado.PENDIENTE)
            ya_asociados = self.instance.cupones_asociados.all()

            # Unimos los querysets
            self.fields['cupones_pendientes'].queryset = pendientes | ya_asociados
            self.fields['cupones_pendientes'].initial = ya_asociados
        else:
            # Si es nueva, no mostramos nada hasta que el usuario elija tarjeta y guarde
            self.fields['cupones_pendientes'].queryset = CuponTarjeta.objects.none()
            self.fields[
                'cupones_pendientes'].help_text = "⚠️ Primero guarde la liquidación para habilitar la selección de cupones."

    def save(self, commit=True):
        liquidacion = super().save(commit=False)
        if commit:
            liquidacion.save()

        if self.instance.pk:
            # Obtener la lista de cupones seleccionados en el widget
            nuevos_seleccionados = self.cleaned_data.get('cupones_pendientes', [])

            # 1. Desvincular los que se desmarcaron (vuelven a estado PENDIENTE)
            for cupon in self.instance.cupones_asociados.all():
                if cupon not in nuevos_seleccionados:
                    cupon.liquidacion = None
                    cupon.estado = CuponTarjeta.Estado.PENDIENTE
                    cupon.save()

            # 2. Vincular los nuevos (pasan a estado PRESENTADO/LIQUIDADO)
            for cupon in nuevos_seleccionados:
                cupon.liquidacion = liquidacion
                cupon.estado = CuponTarjeta.Estado.PRESENTADO
                cupon.save()

            # Recalcular totales automáticamente
            liquidacion.calcular_totales()

        return liquidacion