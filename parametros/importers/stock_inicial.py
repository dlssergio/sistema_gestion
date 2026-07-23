# parametros/importers/stock_inicial.py
from .base import BaseImporter
from inventario.models import Articulo, Deposito, TipoStock, BalanceStock, MovimientoStockLedger, StockArticulo
from parametros.models import CargaMasiva
from decimal import Decimal


class StockInicialImporter(BaseImporter):
    def __init__(self, carga_id):
        super().__init__(carga_id)
        self.articulos_db = {}
        self.depositos_validos_db = set()
        self.tipo_real = None

        self.ledgers_a_crear = []
        self.balances_a_actualizar = []
        self.legacies_a_actualizar = []

    def pre_procesar(self, columnas):
        columnas = [col.replace('*', '') for col in columnas]
        requeridas = ['codigo_articulo', 'deposito_id', 'cantidad']
        for req in requeridas:
            if req not in columnas:
                raise ValueError(f"PLANTILLA INVÁLIDA: Falta la columna obligatoria '{req}'.")

        # Precargamos los IDs para verificar rápidamente
        self.articulos_db = {a.cod_articulo: a.pk for a in Articulo.objects.all()}
        self.depositos_validos_db = set(Deposito.objects.values_list('id', flat=True))

        # El tipo de stock Físico
        self.tipo_real, _ = TipoStock.objects.get_or_create(
            codigo='REAL',
            defaults={'nombre': 'Stock Físico', 'es_fisico': True, 'es_vendible': True}
        )

    def procesar_fila(self, fila, num_fila):
        fila_limpia = {k.replace('*', ''): v for k, v in fila.items()}

        cod_articulo = str(fila_limpia.get('codigo_articulo', '')).strip()
        deposito_str = str(fila_limpia.get('deposito_id', '')).strip()
        observaciones = str(fila_limpia.get('observaciones', '')).strip()

        try:
            cantidad = Decimal(str(fila_limpia.get('cantidad', '0')).replace(',', '.'))
        except:
            raise ValueError(f"Cantidad inválida.")

        if not cod_articulo: raise ValueError("Falta el código de artículo.")
        if not deposito_str.isdigit(): raise ValueError("El ID del depósito debe ser numérico.")

        dep_id = int(deposito_str)

        # Validaciones de integridad
        if cod_articulo not in self.articulos_db:
            raise ValueError(f"El artículo '{cod_articulo}' no existe.")
        if dep_id not in self.depositos_validos_db:
            raise ValueError(f"El depósito ID {dep_id} no existe.")

        art_id = self.articulos_db[cod_articulo]

        # 1. Creamos el registro inmutable (Ledger)
        self.ledgers_a_crear.append(
            MovimientoStockLedger(
                articulo_id=art_id,
                deposito_id=dep_id,
                tipo_stock=self.tipo_real,
                cantidad=cantidad,
                origen_sistema='MIGRACION',
                origen_referencia=f'Saldos Iniciales {self.carga.id}',
                observaciones=observaciones or 'Carga Inicial por Importación'
            )
        )

        # 2. Preparamos las Vistas Materializadas para Upsert
        self.balances_a_actualizar.append(
            BalanceStock(articulo_id=art_id, deposito_id=dep_id, tipo_stock=self.tipo_real, cantidad=cantidad)
        )
        self.legacies_a_actualizar.append(
            StockArticulo(articulo_id=art_id, deposito_id=dep_id, cantidad_real=cantidad)
        )

    def post_procesar(self):
        # 1. Guardar el historial inmutable
        if self.ledgers_a_crear:
            MovimientoStockLedger.objects.bulk_create(self.ledgers_a_crear, batch_size=500)

        # 2. Actualizar las vistas materializadas (con Upsert nativo)
        if self.balances_a_actualizar:
            BalanceStock.objects.bulk_create(
                self.balances_a_actualizar, batch_size=500, update_conflicts=True,
                unique_fields=['articulo', 'deposito', 'tipo_stock'],
                update_fields=['cantidad', 'ultima_actualizacion']
            )

        if self.legacies_a_actualizar:
            StockArticulo.objects.bulk_create(
                self.legacies_a_actualizar, batch_size=500, update_conflicts=True,
                unique_fields=['articulo', 'deposito'],
                update_fields=['cantidad_real']
            )