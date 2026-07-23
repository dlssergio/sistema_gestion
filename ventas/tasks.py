# ventas/tasks.py
import logging
from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)  # Reintenta hasta 3 veces, 5 min entre intentos
def tarea_solicitar_cae(self, comprobante_id, schema_name):
    """
    Tarea asíncrona para solicitar el CAE en AFIP.
    El schema_name es vital porque Celery se ejecuta fuera del scope de la web
    y necesita saber a qué base de datos (tenant) conectarse.
    """
    from django_tenants.utils import schema_context
    from ventas.models import ComprobanteVenta
    from parametros.afip import AfipManager

    logger.info(f"Iniciando solicitud asíncrona de CAE para Comprobante ID {comprobante_id} en tenant '{schema_name}'")

    with schema_context(schema_name):
        try:
            # Volvemos a consultar la DB por si cambió el estado mientras esperaba en la cola
            comp = ComprobanteVenta.objects.get(pk=comprobante_id)

            if comp.cae:
                logger.info(f"Comprobante ID {comprobante_id} ya posee CAE. Omitiendo.")
                return "Ya tiene CAE"

            afip = AfipManager()
            afip.emitir_comprobante(comp)

            comp.refresh_from_db(fields=['cae', 'afip_error'])

            if not comp.cae:
                # Si AFIP devolvió error "suave" pero no CAE
                raise Exception(f"No se obtuvo CAE: {comp.afip_error}")

            return f"CAE exitoso: {comp.cae}"

        except ComprobanteVenta.DoesNotExist:
            logger.error(f"Comprobante ID {comprobante_id} no encontrado en {schema_name}.")
            return "No encontrado"

        except Exception as exc:
            logger.error(f"Fallo en AFIP para Comprobante {comprobante_id}. Reintentando... Error: {str(exc)}")
            # Guardamos el error en la base
            ComprobanteVenta.objects.filter(pk=comprobante_id).update(afip_error=f"Reintentando... {str(exc)}")
            # Le decimos a Celery que intente de nuevo más tarde (lanza excepción Retry)
            raise self.retry(exc=exc)