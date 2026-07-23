# parametros/importers/precios_venta.py
from .base import BaseImporter
from inventario.models import Articulo
from ventas.models import PriceList, ProductPrice
from parametros.models import Moneda, CargaMasiva
from decimal import Decimal
from django.utils.text import slugify


class PrecioVentaImporter(BaseImporter):
    def __init__(self, carga_id):
        super().__init__(carga_id)
        self.moneda_base = None

        # Cachés de alto rendimiento
        self.articulos_db = {}
        self.listas_db = {}
        self.items_lista_db = {}
        self.monedas_db = {}

        # Listas de impacto masivo
        self.items_a_crear = []
        self.items_a_actualizar = []

    def pre_procesar(self, columnas):
        columnas = [col.replace('*', '') for col in columnas]

        # 1. EL CONTRATO ESTRICTO
        columnas_requeridas = ['codigo_articulo', 'precio', 'nombre_lista']
        for col in columnas_requeridas:
            if col not in columnas:
                raise ValueError(f"PLANTILLA INVÁLIDA: Falta la columna obligatoria '{col}'.")

        self.moneda_base = Moneda.objects.filter(es_base=True).first()
        if not self.moneda_base:
            raise ValueError("ERROR DE SISTEMA: No hay una Moneda Base configurada.")

        # Precargar catálogos
        self.articulos_db = {a.cod_articulo: a for a in Articulo.objects.all()}
        for m in Moneda.objects.all():
            self.monedas_db[m.id] = m

        for lista in PriceList.objects.all():
            self.listas_db[lista.name.lower()] = lista

        # Ojo: No cargamos todos los ProductPrice en memoria porque podrían ser cientos de miles.
        # Los cargaremos dinámicamente por Lista (Lazy Loading).

    def procesar_fila(self, fila, num_fila):
        fila_limpia = {k.replace('*', ''): v for k, v in fila.items()}

        cod_articulo = str(fila_limpia.get('codigo_articulo', '')).strip()
        precio_str = str(fila_limpia.get('precio', '')).strip()
        nombre_lista = str(fila_limpia.get('nombre_lista', '')).strip()
        cant_min_str = str(fila_limpia.get('cantidad_minima', '1')).strip()

        # Multimoneda por ID
        moneda_id_str = str(fila_limpia.get('moneda_id', '')).strip()
        moneda_obj = self.moneda_base
        if moneda_id_str.isdigit() and int(moneda_id_str) in self.monedas_db:
            moneda_obj = self.monedas_db[int(moneda_id_str)]

        # --- 1. VALIDACIONES ESTRICTAS POR FILA ---
        if not cod_articulo:
            raise ValueError("El 'codigo_articulo' no puede estar vacío.")
        if not precio_str:
            raise ValueError("El 'precio' no puede estar vacío.")
        if not nombre_lista:
            raise ValueError("El 'nombre_lista' es obligatorio. Ingresa una lista existente o una nueva.")

        try:
            nuevo_precio = Decimal(precio_str.replace(',', '.'))
        except Exception:
            raise ValueError(f"El precio '{precio_str}' no es numérico.")

        try:
            cant_min = Decimal(cant_min_str.replace(',', '.'))
        except Exception:
            cant_min = Decimal('1')

        # --- 2. GESTIÓN DE LISTA DE PRECIOS DE VENTA ---
        nombre_key = nombre_lista.lower()
        if nombre_key not in self.listas_db:
            # Creamos la lista al vuelo. El 'code' debe ser único.
            base_code = slugify(nombre_lista)[:15].upper()
            code = base_code
            counter = 1
            while PriceList.objects.filter(code=code).exists():
                code = f"{base_code}_{counter}"
                counter += 1

            lista = PriceList.objects.create(
                name=nombre_lista,
                code=code,
                is_active=True
            )
            self.listas_db[nombre_key] = lista

        lista_obj = self.listas_db[nombre_key]

        # Lazy Loading: Solo cargamos en memoria los items de esta lista en particular
        cache_lista_key = f"cargada_{lista_obj.pk}"
        if cache_lista_key not in self.listas_db:
            for item in ProductPrice.objects.filter(price_list=lista_obj):
                self.items_lista_db[(lista_obj.pk, item.product_id, item.min_quantity)] = item
            self.listas_db[cache_lista_key] = True

        # --- 3. VALIDACIÓN DE ARTÍCULO ---
        if cod_articulo not in self.articulos_db:
            raise ValueError(f"El artículo '{cod_articulo}' no existe en el catálogo.")
        articulo = self.articulos_db[cod_articulo]

        # --- 4. UPSERT EN LA LISTA DE PRECIOS (Por Escala de Cantidad) ---
        item_key = (lista_obj.pk, articulo.pk, cant_min)
        item_existente = self.items_lista_db.get(item_key)

        if item_existente:
            if item_existente.price_monto != nuevo_precio or item_existente.price_moneda_id != moneda_obj.id:
                item_existente.price_monto = nuevo_precio
                item_existente.price_moneda = moneda_obj
                self.items_a_actualizar.append(item_existente)
        else:
            nuevo_item = ProductPrice(
                price_list=lista_obj,
                product=articulo,
                price_monto=nuevo_precio,
                price_moneda=moneda_obj,
                min_quantity=cant_min
            )
            self.items_a_crear.append(nuevo_item)
            self.items_lista_db[item_key] = nuevo_item

    def post_procesar(self):
        if self.items_a_crear:
            ProductPrice.objects.bulk_create(self.items_a_crear, batch_size=500)

        if self.items_a_actualizar:
            ProductPrice.objects.bulk_update(
                self.items_a_actualizar, ['price_monto', 'price_moneda'], batch_size=500
            )