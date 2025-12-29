# ventas/admin_actions.py
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from .models import ComprobanteVenta, ComprobanteVentaItem
from parametros.models import TipoComprobante


def generar_nota_credito(modeladmin, request, queryset):
    """
    Toma una Factura seleccionada y genera un BORRADOR de Nota de Crédito
    con los mismos ítems, lista para ser editada (ej: borrar lo que no se devolvió).
    """
    if queryset.count() > 1:
        modeladmin.message_user(request, "Por favor seleccione solo una factura para generar NC.", messages.ERROR)
        return

    factura_origen = queryset.first()

    # 1. Determinar el Tipo de NC basado en la Factura (A -> NC A, B -> NC B)
    letra_origen = factura_origen.letra
    try:
        # Buscamos un TipoComprobante que sea NC y tenga la misma letra
        # NOTA: Esto asume que configuraste tus Tipos de Comprobante con código AFIP de NC
        tipo_nc = TipoComprobante.objects.filter(
            nombre__icontains="Nota de Crédito",
            letra=letra_origen
        ).first()

        if not tipo_nc:
            raise ValueError(f"No existe un Tipo de Comprobante 'Nota de Crédito' para la letra {letra_origen}")

    except Exception as e:
        modeladmin.message_user(request, str(e), messages.ERROR)
        return

    # 2. Crear la Cabecera de la NC
    nueva_nc = ComprobanteVenta.objects.create(
        cliente=factura_origen.cliente,
        tipo_comprobante=tipo_nc,
        deposito=factura_origen.deposito,  # Devuelve al mismo depósito
        fecha=timezone.now(),
        estado=ComprobanteVenta.Estado.BORRADOR,
        condicion_venta=factura_origen.condicion_venta,
        comprobante_asociado=factura_origen,  # <--- VINCULACIÓN CLAVE
        observaciones=f"Devolución s/Factura {factura_origen.numero_completo}"
    )

    # 3. Clonar los Ítems
    items_nuevos = []
    for item in factura_origen.items.all():
        items_nuevos.append(ComprobanteVentaItem(
            comprobante=nueva_nc,
            articulo=item.articulo,
            cantidad=item.cantidad,  # Por defecto devolvemos todo, el usuario editará después
            precio_unitario_original=item.precio_unitario_original
        ))

    ComprobanteVentaItem.objects.bulk_create(items_nuevos)

    # 4. Redirigir al usuario a la edición de la nueva NC
    modeladmin.message_user(request,
                            f"Nota de Crédito {nueva_nc.pk} creada en Borrador. Ajuste las cantidades devueltas.",
                            messages.SUCCESS)

    # Truco para redirigir al change_form de la nueva instancia
    url = reverse(f'admin:{nueva_nc._meta.app_label}_{nueva_nc._meta.model_name}_change', args=[nueva_nc.pk])
    return redirect(url)


generar_nota_credito.short_description = "Generar Nota de Crédito por Devolución"