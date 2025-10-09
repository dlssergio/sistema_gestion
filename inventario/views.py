# en inventario/views.py (VERSIÓN FINAL CON get_serializer_class)

from rest_framework import viewsets, filters
from .models import Articulo, Marca, Rubro
# 1. Importamos ambos serializers de Artículo
from .serializers import ArticuloSerializer, ArticuloCreateUpdateSerializer, MarcaSerializer, RubroSerializer

class ArticuloViewSet(viewsets.ModelViewSet):
    queryset = Articulo.objects.all().order_by('cod_articulo')
    filter_backends = [filters.SearchFilter]
    search_fields = ['cod_articulo', 'descripcion', 'ean']

    # 2. AÑADIMOS EL MÉTODO PARA SELECCIONAR EL SERIALIZER
    def get_serializer_class(self):
        # Si la acción es crear (POST) o actualizar (PUT/PATCH)...
        if self.action in ['create', 'update', 'partial_update']:
            # ...usamos el serializer de escritura.
            return ArticuloCreateUpdateSerializer
        # Para cualquier otra acción (list, retrieve)...
        # ...usamos el serializer de lectura.
        return ArticuloSerializer

# ... (El resto de los ViewSets de Marca y Rubro no cambian) ...
class MarcaViewSet(viewsets.ModelViewSet):
    queryset = Marca.objects.all().order_by('nombre')
    serializer_class = MarcaSerializer
    search_fields = ['nombre']

class RubroViewSet(viewsets.ModelViewSet):
    queryset = Rubro.objects.all().order_by('nombre')
    serializer_class = RubroSerializer
    search_fields = ['nombre']