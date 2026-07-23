# parametros/importers/articulos.py
from .base import BaseImporter
from inventario.models import Articulo, Marca, Rubro
from parametros.models import Moneda, UnidadMedida, Impuesto, CargaMasiva
from decimal import Decimal


class ArticuloImporter(BaseImporter):
    def __init__(self, carga_id):
        super().__init__(carga_id)

        # Cachés
        self.articulos_db = {}
        self.marcas_db = {}
        self.rubros_db = {}
        self.unidades_db = {}
        self.monedas_db = {}
        self.impuestos_validos_db = set()

        self.moneda_base = None
        self.unidad_base = None

        self.articulos_a_crear = []
        self.articulos_a_actualizar = []

        # Para el M2M de impuestos por ID: {cod_articulo_interno: [1, 2, 5]}
        self.relaciones_impuestos = {}

    def pre_procesar(self, columnas):
        # Limpiar asteriscos de las columnas
        columnas = [col.replace('*', '') for col in columnas]

        # 1. Contrato de Datos Estricto
        requeridas = ['codigo_articulo', 'descripcion', 'precio_costo']
        for req in requeridas:
            if req not in columnas:
                raise ValueError(f"PLANTILLA INVÁLIDA: Falta la columna obligatoria '{req}'.")

        self.moneda_base = Moneda.objects.filter(es_base=True).first()
        self.unidad_base = UnidadMedida.objects.first()

        if not self.moneda_base or not self.unidad_base:
            raise ValueError("ERROR: Falta Moneda o Unidad de Medida base en el sistema.")

        # 2. Precarga de Catálogos (Velocidad extrema)
        self.articulos_db = {a.cod_articulo: a for a in Articulo.objects.all()}
        self.marcas_db = {m.nombre.lower(): m for m in Marca.objects.all()}
        self.rubros_db = {r.nombre.lower(): r for r in Rubro.objects.all()}

        # Guardamos un Set con los IDs de impuestos reales para evitar errores si el usuario tipea mal un ID
        self.impuestos_validos_db = set(Impuesto.objects.values_list('id', flat=True))

        # Cargamos las unidades de medida buscables por ID y por Símbolo
        for u in UnidadMedida.objects.all():
            self.unidades_db[str(u.id)] = u
            self.unidades_db[u.simbolo.lower()] = u

        # Precargamos las monedas referenciadas estrcitamente por su ID
        for m in Moneda.objects.all():
            self.monedas_db[m.id] = m

    def _parse_decimal(self, value, default='0'):
        try:
            return Decimal(str(value).replace(',', '.').strip() or default)
        except:
            return Decimal(default)

    def _parse_bool(self, value):
        return str(value).strip().upper() in ['S', 'SI', '1', 'TRUE', 'Y', 'YES']

    def procesar_fila(self, fila, num_fila):
        fila_limpia = {k.replace('*', ''): v for k, v in fila.items()}

        cod_articulo = str(fila_limpia.get('codigo_articulo', '')).strip()
        descripcion = str(fila_limpia.get('descripcion', '')).strip()

        # --- 1. CONTROLES OBLIGATORIOS ---
        if not cod_articulo or not descripcion:
            raise ValueError("El 'codigo_articulo' y 'descripcion' son obligatorios.")

        # --- 2. EXTRACCIÓN Y TRANSFORMACIÓN DE DATOS ---
        ean = str(fila_limpia.get('ean', '')).strip()
        qr = str(fila_limpia.get('qr', '')).strip()
        desc_larga = str(fila_limpia.get('descripcion_larga', '')).strip()
        cod_fab = str(fila_limpia.get('cod_fabricante', '')).strip()

        # Booleanos
        es_servicio = self._parse_bool(fila_limpia.get('es_servicio', 'N'))
        es_bien_de_uso = self._parse_bool(fila_limpia.get('es_bien_de_uso', 'N'))

        # Numéricos
        precio_costo = self._parse_decimal(fila_limpia.get('precio_costo', '0'))
        utilidad = self._parse_decimal(fila_limpia.get('utilidad', fila_limpia.get('margen_utilidad', '0')))

        stock_min = self._parse_decimal(fila_limpia.get('stock_minimo', '0'))
        stock_max = self._parse_decimal(fila_limpia.get('stock_maximo', '0'))
        stock_seg = self._parse_decimal(fila_limpia.get('stock_seguridad', '0'))

        peso = self._parse_decimal(fila_limpia.get('peso_kg', '0'))
        alto = self._parse_decimal(fila_limpia.get('alto_cm', '0'))
        ancho = self._parse_decimal(fila_limpia.get('ancho_cm', '0'))
        prof = self._parse_decimal(fila_limpia.get('profundidad_cm', '0'))

        ubicacion = str(fila_limpia.get('ubicacion', '')).strip()
        nota = str(fila_limpia.get('nota', '')).strip()

        # --- GESTIÓN DE RELACIONES ---
        marca_obj = None
        marca_str = str(fila_limpia.get('marca', '')).strip()
        if marca_str:
            marca_key = marca_str.lower()
            if marca_key not in self.marcas_db:
                self.marcas_db[marca_key] = Marca.objects.create(nombre=marca_str)
            marca_obj = self.marcas_db[marca_key]

        rubro_obj = None
        rubro_str = str(fila_limpia.get('rubro', '')).strip()
        if rubro_str:
            rubro_key = rubro_str.lower()
            if rubro_key not in self.rubros_db:
                self.rubros_db[rubro_key] = Rubro.objects.create(nombre=rubro_str)
            rubro_obj = self.rubros_db[rubro_key]

        if not rubro_obj and not es_servicio:
            if 'general' not in self.rubros_db:
                self.rubros_db['general'] = Rubro.objects.create(nombre="General")
            rubro_obj = self.rubros_db['general']

        # --- GESTIÓN DE UNIDADES DE MEDIDA ---
        um_stock_str = str(fila_limpia.get('unidad_medida_stock', '')).strip().lower()
        um_venta_str = str(fila_limpia.get('unidad_medida_venta', '')).strip().lower()
        um_stock_obj = self.unidades_db.get(um_stock_str, self.unidad_base) if um_stock_str else self.unidad_base
        um_venta_obj = self.unidades_db.get(um_venta_str, self.unidad_base) if um_venta_str else self.unidad_base

        # --- MULTIMONEDA POR ID ESTRICTO ---
        m_costo_id_str = str(fila_limpia.get('moneda_costo_id', '')).strip()
        m_venta_id_str = str(fila_limpia.get('moneda_venta_id', '')).strip()

        moneda_costo_obj = self.moneda_base
        if m_costo_id_str.isdigit() and int(m_costo_id_str) in self.monedas_db:
            moneda_costo_obj = self.monedas_db[int(m_costo_id_str)]

        moneda_venta_obj = self.moneda_base
        if m_venta_id_str.isdigit() and int(m_venta_id_str) in self.monedas_db:
            moneda_venta_obj = self.monedas_db[int(m_venta_id_str)]

        # --- GESTIÓN DE IMPUESTOS ---
        impuestos_ids_str = str(fila_limpia.get('impuestos_ids', '')).replace(' ', '')
        impuestos_ids = []
        if impuestos_ids_str:
            for i in impuestos_ids_str.split(','):
                if i.isdigit() and int(i) in self.impuestos_validos_db:
                    impuestos_ids.append(int(i))

        # --- UPSERT DEL ARTÍCULO ---
        articulo = self.articulos_db.get(cod_articulo)

        if articulo:
            if self.modo == CargaMasiva.Modo.CREAR:
                raise ValueError(f"El artículo '{cod_articulo}' ya existe.")

            articulo.descripcion = descripcion
            articulo.ean = str(fila_limpia.get('ean', articulo.ean)).strip()
            articulo.qr = str(fila_limpia.get('qr', articulo.qr)).strip()
            articulo.descripcion_larga = str(fila_limpia.get('descripcion_larga', articulo.descripcion_larga)).strip()
            articulo.cod_fabricante = str(fila_limpia.get('cod_fabricante', articulo.cod_fabricante)).strip()

            if marca_obj: articulo.marca = marca_obj
            if rubro_obj: articulo.rubro = rubro_obj

            articulo.es_servicio = es_servicio
            articulo.es_bien_de_uso = es_bien_de_uso

            articulo.unidad_medida_stock = um_stock_obj
            articulo.unidad_medida_venta = um_venta_obj

            # Asignación de Montos y Monedas por ID
            articulo.precio_costo_monto = precio_costo
            articulo.precio_costo_moneda = moneda_costo_obj
            articulo.utilidad = utilidad

            # Recálculo Venta
            utilidad_decimal = Decimal(str(articulo.utilidad or 0))
            nuevo_precio_venta = precio_costo * (Decimal('1') + (utilidad_decimal / Decimal('100')))
            articulo.precio_venta_monto = nuevo_precio_venta
            articulo.precio_venta_moneda = moneda_venta_obj

            articulo.stock_minimo = stock_min
            articulo.stock_maximo = stock_max
            articulo.stock_seguridad = stock_seg

            if peso > 0: articulo.peso_kg = peso
            if alto > 0: articulo.alto_cm = alto
            if ancho > 0: articulo.ancho_cm = ancho
            if prof > 0: articulo.profundidad_cm = prof

            articulo.ubicacion = ubicacion
            articulo.nota = nota

            self.articulos_a_actualizar.append(articulo)
            if impuestos_ids:
                self.relaciones_impuestos[cod_articulo] = impuestos_ids

        else:
            if self.modo == CargaMasiva.Modo.ACTUALIZAR:
                raise ValueError(f"El artículo '{cod_articulo}' no existe.")

            # Recálculo Venta inicial
            utilidad_decimal = Decimal(str(utilidad or 0))
            nuevo_precio_venta = precio_costo * (Decimal('1') + (utilidad_decimal / Decimal('100')))

            nuevo_articulo = Articulo(
                cod_articulo=cod_articulo,
                descripcion=descripcion,
                ean=ean,
                qr=qr,
                descripcion_larga=desc_larga,
                cod_fabricante=cod_fab,
                marca=marca_obj,
                rubro=rubro_obj,
                es_servicio=es_servicio,
                es_bien_de_uso=es_bien_de_uso,
                precio_costo_monto=precio_costo,
                precio_costo_moneda=moneda_costo_obj,
                utilidad=utilidad,
                precio_venta_monto=nuevo_precio_venta,
                precio_venta_moneda=moneda_venta_obj,
                unidad_medida_stock=um_stock_obj,
                unidad_medida_venta=um_venta_obj,
                stock_minimo=stock_min,
                stock_maximo=stock_max,
                stock_seguridad=stock_seg,
                peso_kg=peso if peso > 0 else None,
                alto_cm=alto if alto > 0 else None,
                ancho_cm=ancho if ancho > 0 else None,
                profundidad_cm=prof if prof > 0 else None,
                ubicacion=ubicacion,
                nota=nota,
                is_active=True
            )
            self.articulos_a_crear.append(nuevo_articulo)
            self.articulos_db[cod_articulo] = nuevo_articulo
            if impuestos_ids:
                self.relaciones_impuestos[cod_articulo] = impuestos_ids

    def post_procesar(self):
        # 1. VOLCADO MASIVO
        if self.articulos_a_crear:
            Articulo.objects.bulk_create(self.articulos_a_crear, batch_size=500)

        if self.articulos_a_actualizar:
            Articulo.objects.bulk_update(
                self.articulos_a_actualizar,
                [
                    'descripcion', 'ean', 'qr', 'descripcion_larga', 'cod_fabricante', 'marca', 'rubro',
                    'es_servicio', 'es_bien_de_uso',
                    'precio_costo_monto', 'precio_costo_moneda',
                    'utilidad',
                    'precio_venta_monto', 'precio_venta_moneda',
                    'unidad_medida_stock', 'unidad_medida_venta',
                    'stock_minimo', 'stock_maximo', 'stock_seguridad', 'peso_kg', 'alto_cm', 'ancho_cm',
                    'profundidad_cm', 'ubicacion', 'nota'
                ],
                batch_size=500
            )

        if self.relaciones_impuestos:
            codigos_involucrados = list(self.relaciones_impuestos.keys())
            arts_actuales = {a.cod_articulo: a for a in Articulo.objects.filter(cod_articulo__in=codigos_involucrados)}
            for cod, lista_ids_impuestos in self.relaciones_impuestos.items():
                if cod in arts_actuales:
                    arts_actuales[cod].impuestos.set(lista_ids_impuestos)