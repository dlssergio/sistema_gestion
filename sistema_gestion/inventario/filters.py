# inventario/filters.py

from django.db.models import Q
from rest_framework import filters


class ArticuloSearchFilter(filters.BaseFilterBackend):
    """
    Filtro de búsqueda para Articulo que trata el query como una cadena completa,
    a diferencia del SearchFilter estándar de DRF que tokeniza por espacios y
    genera un AND por cada token, lo que devuelve resultados inesperados.

    Parámetros GET aceptados:
      search       : texto a buscar (cadena completa, sin tokenizar)
      search_field : campo donde buscar
                       'all'           → todos los campos (OR entre ellos)  ← default
                       'cod_articulo'  → solo código de artículo
                       'descripcion'   → solo descripción
                       'ean'           → solo código de barras EAN
                       'marca'         → solo nombre de marca
                       'rubro'         → solo nombre de rubro
      search_mode  : tipo de coincidencia
                       'contains'      → icontains  ← default
                       'starts'        → istartswith
                       'ends'          → iendswith
                       'exact'         → iexact

    Ejemplos:
      /api/articulos/?search=pañal
      /api/articulos/?search=AR00&search_field=cod_articulo&search_mode=starts
      /api/articulos/?search=Philips&search_field=marca
      /api/articulos/?search=001&search_field=ean&search_mode=ends
    """

    # Mapeo de search_field → campo ORM de Django
    FIELD_LOOKUPS = {
        'cod_articulo': 'cod_articulo',
        'descripcion':  'descripcion',
        'ean':          'ean',
        'marca':        'marca__nombre',
        'rubro':        'rubro__nombre',
    }

    # Mapeo de search_mode → sufijo de lookup Django
    MODE_SUFFIX = {
        'contains': 'icontains',
        'starts':   'istartswith',
        'ends':     'iendswith',
        'exact':    'iexact',
    }

    def filter_queryset(self, request, queryset, view):
        search = (request.query_params.get('search') or '').strip()
        if not search:
            return queryset

        field = request.query_params.get('search_field', 'all')
        mode  = request.query_params.get('search_mode',  'contains')

        # Normalizar valores desconocidos → defaults seguros
        if mode not in self.MODE_SUFFIX:
            mode = 'contains'
        suffix = self.MODE_SUFFIX[mode]

        if field == 'all' or field not in self.FIELD_LOOKUPS:
            # Busca en todos los campos configurados con OR
            # El texto se trata como una cadena completa — no se tokeniza
            q_filter = (
                Q(**{f'cod_articulo__{suffix}':  search}) |
                Q(**{f'descripcion__{suffix}':   search}) |
                Q(**{f'ean__{suffix}':           search}) |
                Q(**{f'marca__nombre__{suffix}': search}) |
                Q(**{f'rubro__nombre__{suffix}': search})
            )
            return queryset.filter(q_filter).distinct()
        else:
            orm_field = self.FIELD_LOOKUPS[field]
            return queryset.filter(**{f'{orm_field}__{suffix}': search})