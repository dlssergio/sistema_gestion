# parametros/importers/precios_compra.py
from .base import BaseImporter
from inventario.models import Articulo
from compras.models import (
    ListaPreciosProveedor, ItemListaPreciosProveedor, HistorialPrecioProveedor, Proveedor
)
from parametros.models import Moneda, UnidadMedida
from decimal import Decimal


class PrecioCompraImporter(BaseImporter):
    def __init__(self, carga_id):
        super().__init__(carga_id)
        self.moneda_base = None
        self.unidad_base = None

        # Cachés de alto rendimiento
        self.articulos_db = {}
        self.listas_db = {}
        self.items_lista_db = {}
        self.monedas_db = {}

        # Listas de impacto masivo
        self.items_a_crear = []
        self.items_a_actualizar = []
        self.historial_a_crear = []
        self.articulos_a_actualizar = {}

    def pre_procesar(self, columnas):
        # Limpiamos asteriscos para leer seguro
        columnas = [col.replace('*', '') for col in columnas]

        # 1. EL CONTRATO ESTRICTO: Validación de Formato
        columnas_requeridas = ['codigo_articulo', 'precio', 'nombre_lista', 'actualiza_costo']
        if 'cuit_proveedor' not in columnas and 'codigo_proveedor' not in columnas:
            raise ValueError("PLANTILLA INVÁLIDA: Falta columna 'cuit_proveedor' o 'codigo_proveedor'.")

        for col in columnas_requeridas:
            if col not in columnas:
                raise ValueError(f"PLANTILLA INVÁLIDA: Falta la columna obligatoria '{col}'.")

        self.moneda_base = Moneda.objects.filter(es_base=True).first()
        self.unidad_base = UnidadMedida.objects.first()

        if not self.moneda_base:
            raise ValueError("ERROR DE SISTEMA: No hay una Moneda Base configurada.")

        # Precargar catálogo de artículos y de monedas (Por ID estrictamente)
        self.articulos_db = {a.cod_articulo: a for a in Articulo.objects.all()}
        for m in Moneda.objects.all():
            self.monedas_db[m.id] = m

    def procesar_fila(self, fila, num_fila):
        fila_limpia = {k.replace('*', ''): v for k, v in fila.items()}

        cuit_prov = fila_limpia.get('cuit_proveedor', '').replace("-", "").strip()
        cod_prov = fila_limpia.get('codigo_proveedor', '').strip()
        cod_articulo = fila_limpia.get('codigo_articulo', '').strip()
        precio_str = fila_limpia.get('precio', '').strip()
        nombre_lista = fila_limpia.get('nombre_lista', '').strip()
        actualiza_costo_str = str(fila_limpia.get('actualiza_costo', '')).strip().upper()

        # --- MULTIMONEDA POR ID ---
        moneda_id_str = str(fila_limpia.get('moneda_id', '')).strip()
        moneda_obj = self.moneda_base
        if moneda_id_str.isdigit() and int(moneda_id_str) in self.monedas_db:
            moneda_obj = self.monedas_db[int(moneda_id_str)]

        # --- 1. VALIDACIONES ESTRICTAS POR FILA ---
        identificador = cuit_prov or cod_prov
        if not identificador:
            raise ValueError("Falta CUIT o Código del Proveedor.")
        if not cod_articulo:
            raise ValueError("El 'codigo_articulo' no puede estar vacío.")
        if not precio_str:
            raise ValueError("El 'precio' no puede estar vacío.")
        if not nombre_lista:
            raise ValueError("El 'nombre_lista' es obligatorio. Ingresa una lista existente o una nueva.")
        if actualiza_costo_str not in ['S', 'SI', '1', 'N', 'NO', '0']:
            raise ValueError(f"Valor '{actualiza_costo_str}' inválido en 'actualiza_costo'. Usa 'S' o 'N'.")

        try:
            nuevo_precio = Decimal(precio_str.replace(',', '.'))
        except Exception:
            raise ValueError(f"El precio '{precio_str}' no es numérico.")

        # Flag booleano de actualización maestra
        actualiza_costo_maestro = actualiza_costo_str in ['S', 'SI', '1']

        # --- 2. GESTIÓN DE PROVEEDOR Y LISTA ---
        cache_key_lista = f"{identificador}_{nombre_lista}"

        if cache_key_lista not in self.listas_db:
            if cuit_prov:
                prov = Proveedor.objects.filter(entidad__cuit=cuit_prov).first()
            else:
                prov = Proveedor.objects.filter(codigo_proveedor=cod_prov).first()

            if not prov:
                raise ValueError(f"No existe proveedor con identificador: '{identificador}'")

            # MAGIA 1: Si la lista existe con ese nombre, la trae. Si no, la crea.
            lista, creada = ListaPreciosProveedor.objects.get_or_create(
                proveedor_id=prov.pk,
                nombre=nombre_lista
            )

            # MAGIA 2: Solución al bug de lista "Inactiva" para ERPBaseModel
            if creada:
                if hasattr(lista, 'es_activa'): lista.es_activa = True
                if hasattr(lista, 'is_active'): lista.is_active = True
                if hasattr(lista, 'estado'): lista.estado = 'ACT'
                if hasattr(lista, 'es_principal'): lista.es_principal = True
                lista.save()

            self.listas_db[cache_key_lista] = lista

            # Precargamos los items de ESTA lista
            for item in ItemListaPreciosProveedor.objects.filter(lista_precios=lista):
                self.items_lista_db[(lista.pk, item.articulo_id)] = item

        lista_obj = self.listas_db[cache_key_lista]

        # --- 3. VALIDACIÓN DE ARTÍCULO ---
        if cod_articulo not in self.articulos_db:
            raise ValueError(f"El artículo '{cod_articulo}' no existe en el catálogo.")
        articulo = self.articulos_db[cod_articulo]

        # --- 4. UPSERT EN LA LISTA DE PRECIOS ---
        item_key = (lista_obj.pk, articulo.pk)
        item_existente = self.items_lista_db.get(item_key)

        if item_existente:
            precio_anterior = item_existente.precio_lista_monto
            if precio_anterior != nuevo_precio or item_existente.precio_lista_moneda_id != moneda_obj.id:
                item_existente.precio_lista_monto = nuevo_precio
                item_existente.precio_lista_moneda = moneda_obj  # <--- Actualiza la Moneda
                self.items_a_actualizar.append(item_existente)

                from djmoney.money import Money
                hist = HistorialPrecioProveedor(
                    item=item_existente,
                    precio_lista_anterior=precio_anterior,
                    precio_lista_anterior_currency=self.moneda_base.simbolo,
                    precio_lista_nuevo=nuevo_precio,
                    precio_lista_nuevo_currency=self.moneda_base.simbolo,
                    motivo=f"Importación CSV"
                )
                self.historial_a_crear.append(hist)
        else:
            nuevo_item = ItemListaPreciosProveedor(
                lista_precios=lista_obj,
                articulo=articulo,
                unidad_medida_compra=self.unidad_base,
                precio_lista_monto=nuevo_precio,
                precio_lista_moneda=moneda_obj,  # <--- Asigna la Moneda
                cantidad_minima=1,
                descuentos_adicionales=[],
                descuentos_financieros=[]
            )
            self.items_a_crear.append(nuevo_item)
            self.items_lista_db[item_key] = nuevo_item

        # --- 5. CASCADA FINANCIERA (Controlada por el Usuario) ---
        if actualiza_costo_maestro:
            art_to_update = self.articulos_a_actualizar.get(articulo.pk, articulo)

            art_to_update.precio_costo_monto = nuevo_precio
            art_to_update.precio_costo_moneda = moneda_obj  # <--- Asigna la moneda al costo del Articulo

            # Recalcula el precio de venta conservando la utilidad del producto
            utilidad = getattr(art_to_update, 'margen_utilidad', getattr(art_to_update, 'utilidad', 0)) or 0
            utilidad_decimal = Decimal(str(utilidad))
            nuevo_precio_venta = nuevo_precio * (Decimal('1') + (utilidad_decimal / Decimal('100')))

            art_to_update.precio_venta_monto = nuevo_precio_venta
            art_to_update.precio_venta_moneda = moneda_obj  # Vincula la moneda de venta
            self.articulos_a_actualizar[articulo.pk] = art_to_update

    def post_procesar(self):
        if self.items_a_crear:
            ItemListaPreciosProveedor.objects.bulk_create(self.items_a_crear, batch_size=500)

        if self.items_a_actualizar:
            ItemListaPreciosProveedor.objects.bulk_update(
                self.items_a_actualizar, ['precio_lista_monto', 'precio_lista_moneda'], batch_size=500
            )

        if self.historial_a_crear:
            HistorialPrecioProveedor.objects.bulk_create(self.historial_a_crear, batch_size=500)

        if self.articulos_a_actualizar:
            Articulo.objects.bulk_update(
                self.articulos_a_actualizar.values(),
                ['precio_costo_monto', 'precio_costo_moneda', 'precio_venta_monto', 'precio_venta_moneda'],
                batch_size=500
            )