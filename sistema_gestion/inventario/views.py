# en inventario/views.py (VERSIÓN FINAL CON get_serializer_class)

from rest_framework import viewsets, filters
from .models import Articulo, Marca, Rubro, CategoriaImpositiva
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