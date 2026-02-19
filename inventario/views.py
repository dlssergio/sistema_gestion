# inventario/views.py

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, get_object_or_404
from django.db.models import F, Q, Sum, DecimalField
from django.utils import timezone
from rest_framework import viewsets, filters
from .models import (
    Articulo, Marca,
    Rubro, CategoriaImpositiva,
    MovimientoStockLedger, BalanceStock,
    Deposito, TipoStock
)
from .serializers import (
    ArticuloSerializer,
    ArticuloCreateUpdateSerializer,
    MarcaSerializer,
    RubroSerializer,
    CategoriaImpositivaSerializer
)
from rest_framework.decorators import action
from rest_framework.response import Response

class ArticuloViewSet(viewsets.ModelViewSet):
    queryset = Articulo.objects.all().order_by('cod_articulo')
    filter_backends = [filters.SearchFilter]
    search_fields = [
        'cod_articulo',
        'descripcion',
        'ean',
        'qr',
        'marca__nombre',  # Busca por el nombre de la marca relacionada
        'rubro__nombre'  # Busca por el nombre del rubro relacionado
    ]

    # 2. AÑADIMOS EL MÉTODO PARA SELECCIONAR EL SERIALIZER
    def get_serializer_class(self):
        # Si la acción es crear (POST) o actualizar (PUT/PATCH)...
        if self.action in ['create', 'update', 'partial_update']:
            # ...usamos el serializer de escritura.
            return ArticuloCreateUpdateSerializer
        # Para cualquier otra acción (list, retrieve)...
        # ...usamos el serializer de lectura.
        return ArticuloSerializer

    @action(detail=False, methods=['get'])
    def choices(self, request):
        """Devuelve las opciones para los selects del formulario"""
        return Response({
            'perfil': Articulo.Perfil.choices,
            # Agrega aquí otros choices si tuvieras
        })

# ... (El resto de los ViewSets de Marca y Rubro no cambian) ...
class MarcaViewSet(viewsets.ModelViewSet):
    queryset = Marca.objects.all().order_by('nombre')
    serializer_class = MarcaSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['nombre']

class RubroViewSet(viewsets.ModelViewSet):
    queryset = Rubro.objects.all().order_by('nombre')
    serializer_class = RubroSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['nombre']

class CategoriaImpositivaViewSet(viewsets.ModelViewSet):
    queryset = CategoriaImpositiva.objects.all()
    serializer_class = CategoriaImpositivaSerializer


@staff_member_required
def kardex_articulo_view(request, articulo_id):
    articulo = get_object_or_404(Articulo, pk=articulo_id)

    # Obtenemos todos los movimientos históricos ordenados cronológicamente
    movimientos = MovimientoStockLedger.objects.filter(
        articulo=articulo
    ).order_by('fecha_movimiento', 'pk')

    # Filtros opcionales desde la URL (por ejemplo ?deposito=1)
    deposito_id = request.GET.get('deposito')
    if deposito_id:
        movimientos = movimientos.filter(deposito_id=deposito_id)

    # Lógica de "Running Balance" (Saldo Acumulado)
    # Django ORM no hace esto nativamente de forma eficiente, así que lo hacemos en Python
    # dado que paginar un Kardex rompe el cálculo del saldo anterior.

    filas = []
    saldo_acumulado = 0

    for mov in movimientos:
        # Solo sumamos al saldo visible si es stock REAL (Físico)
        # Si quieres ver también el comprometido, habría que desdoblar columnas.
        # Por ahora, Kardex Físico Estándar.

        impacto = 0
        if mov.tipo_stock.es_fisico:  # Asumiendo que definimos este flag, o usamos codigo='REAL'
            impacto = mov.cantidad

        saldo_acumulado += impacto

        filas.append({
            'fecha': mov.fecha_movimiento,
            'origen': mov.origen_sistema,
            'referencia': mov.origen_referencia,
            'deposito': mov.deposito.nombre,
            'tipo': mov.tipo_stock.nombre,
            'entrada': mov.cantidad if mov.cantidad > 0 else 0,
            'salida': abs(mov.cantidad) if mov.cantidad < 0 else 0,
            'saldo': saldo_acumulado,
            'usuario': mov.usuario
        })

    # Invertimos la lista para ver lo más reciente arriba (opcional, pero útil en web)
    # filas = list(reversed(filas))
    # El Kardex contable suele leerse de arriba (viejo) a abajo (nuevo). Lo dejamos normal.

    context = {
        'articulo': articulo,
        'filas': filas,
        'saldo_final': saldo_acumulado,
        'title': f"Ficha de Stock (Kardex): {articulo.descripcion}"
    }

    return render(request, 'admin/inventario/articulo/kardex.html', context)


@staff_member_required
def reporte_valorizacion_view(request):
    # 1. Filtros
    deposito_id = request.GET.get('deposito')

    # 2. Query Base: Solo stock REAL (Físico) y mayor a 0
    # Usamos select_related para evitar el problema de N+1 queries
    queryset = BalanceStock.objects.filter(
        tipo_stock__codigo='REAL',
        cantidad__gt=0
    ).select_related('articulo', 'deposito', 'articulo__precio_costo_moneda')

    if deposito_id:
        queryset = queryset.filter(deposito_id=deposito_id)
        nombre_deposito = Deposito.objects.get(pk=deposito_id).nombre
    else:
        nombre_deposito = "TODOS LOS DEPÓSITOS"

    # 3. Procesamiento en Python (para cálculos de moneda y totales)
    lineas = []
    total_general_stock = 0
    total_general_valor = 0

    # Obtenemos el símbolo de moneda base (ej: ARS) para mostrar
    moneda_base = "ARS"

    for balance in queryset:
        art = balance.articulo
        cantidad = balance.cantidad
        costo = art.precio_costo_monto  # Asumimos costo en moneda base

        # Si tienes multimoneda real, aquí deberías convertir el costo.
        # Por ahora asumimos que el reporte es en moneda base.

        subtotal_valor = cantidad * costo

        total_general_stock += cantidad
        total_general_valor += subtotal_valor

        lineas.append({
            'codigo': art.cod_articulo,
            'descripcion': art.descripcion,
            'rubro': art.rubro.nombre if art.rubro else '-',
            'deposito': balance.deposito.nombre,
            'cantidad': cantidad,
            'costo': costo,
            'total': subtotal_valor
        })

    # 4. Contexto para el template
    context = {
        'lineas': lineas,
        'total_stock': total_general_stock,
        'total_valor': total_general_valor,
        'depositos': Deposito.objects.all(),
        'deposito_actual': int(deposito_id) if deposito_id else None,
        'nombre_deposito': nombre_deposito,
        'fecha_emision': timezone.now(),
        'moneda': moneda_base,
        'title': "Reporte de Valorización de Inventario"
    }

    return render(request, 'admin/inventario/balance_stock/reporte_valorizacion.html', context)