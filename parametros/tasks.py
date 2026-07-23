# parametros/tasks.py
from celery import shared_task
from django_tenants.utils import schema_context
from parametros.models import CargaMasiva
from parametros.importers.contactos import ContactoImporter
from parametros.importers.precios_compra import PrecioCompraImporter
from parametros.importers.articulos import ArticuloImporter
from parametros.importers.stock_inicial import StockInicialImporter
from parametros.importers.precios_venta import PrecioVentaImporter

@shared_task
def procesar_carga_masiva_task(carga_id, schema_name):
    with schema_context(schema_name):
        try:
            carga = CargaMasiva.objects.get(id=carga_id)
        except CargaMasiva.DoesNotExist:
            return False

        carga.estado = CargaMasiva.Estado.PROCESANDO
        carga.save(update_fields=['estado'])

        # EL ENRUTADOR MAESTRO DE IMPORTACIONES
        try:
            if carga.entidad == CargaMasiva.Entidad.PROVEEDORES:
                importer = ContactoImporter(carga_id, tipo_contacto='PROVEEDOR')
                importer.procesar()

            elif carga.entidad == CargaMasiva.Entidad.CLIENTES:
                importer = ContactoImporter(carga_id, tipo_contacto='CLIENTE')
                importer.procesar()

            elif carga.entidad == CargaMasiva.Entidad.PRECIOS_COMPRA:
                importer = PrecioCompraImporter(carga_id)
                importer.procesar()

            elif carga.entidad == CargaMasiva.Entidad.PRECIOS_VENTA:
                importer = PrecioVentaImporter(carga_id)
                importer.procesar()

            elif carga.entidad == CargaMasiva.Entidad.ARTICULOS:
                importer = ArticuloImporter(carga_id)
                importer.procesar()

            elif carga.entidad == CargaMasiva.Entidad.STOCK_INICIAL:
                importer = StockInicialImporter(carga_id)
                importer.procesar()

            else:
                raise ValueError(f"Entidad '{carga.entidad}' no soportada aún.")

        except Exception as e:
            carga.estado = CargaMasiva.Estado.ERROR
            carga.detalle_errores = [{"fila": "Error Crítico del Sistema", "error": str(e)}]
            carga.save(update_fields=['estado', 'detalle_errores'])
            return False

        return True