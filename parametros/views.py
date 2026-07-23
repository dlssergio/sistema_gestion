# parametros/views.py (VERSIÓN FINAL Y ROBUSTA)

from rest_framework import viewsets, mixins
from .models import Moneda, TipoComprobante, Impuesto, CategoriaImpositiva, ConfiguracionEmpresa, CargaMasiva, \
    UnidadMedida, SerieDocumento, ReglaConversionComprobante
from .serializers import (
    MonedaSerializer, TipoComprobanteSerializer, ImpuestoSerializer,
    CategoriaImpositivaSerializer, ConfiguracionEmpresaSerializer,
    CargaMasivaSerializer, ReglaConversionSerializer
)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import action
from django.http import HttpResponse
from django.db import transaction
import csv
import threading  # Temporalmente, hasta que enlacemos Celery en el paso 2


class MonedaViewSet(viewsets.ModelViewSet):
    """
    API endpoint que permite ver las Monedas.
    """
    queryset = Moneda.objects.all()
    serializer_class = MonedaSerializer


class TipoComprobanteViewSet(viewsets.ModelViewSet):
    """
    API endpoint que permite ver los Tipos de Comprobante.
    """
    queryset = TipoComprobante.objects.all()
    serializer_class = TipoComprobanteSerializer


# <<< SE ELIMINA 'ReglaImpuestoViewSet' POR COMPLETO >>>

# --- ViewSets para la Nueva Arquitectura de Impuestos ---

class ImpuestoViewSet(viewsets.ModelViewSet):
    queryset = Impuesto.objects.all()
    serializer_class = ImpuestoSerializer


class CategoriaImpositivaViewSet(viewsets.ModelViewSet):
    """
    API endpoint que permite ver y gestionar las Reglas de Impuesto.
    """
    queryset = CategoriaImpositiva.objects.all()
    serializer_class = CategoriaImpositivaSerializer


class ConfiguracionEmpresaView(APIView):
    """
    Devuelve la configuración de la empresa actual.
    Si no existe, devuelve vacío o un error controlado.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        config = ConfiguracionEmpresa.objects.first()
        if config:
            serializer = ConfiguracionEmpresaSerializer(config)
            return Response(serializer.data)
        return Response({"detail": "Empresa no configurada"}, status=404)


class CargaMasivaViewSet(viewsets.ModelViewSet):
    """
    API para gestionar la carga de archivos masivos y consultar su progreso.
    """
    queryset = CargaMasiva.objects.all()
    serializer_class = CargaMasivaSerializer
    parser_classes = (MultiPartParser, FormParser)  # <--- FUNDAMENTAL PARA RECIBIR ARCHIVOS

    def perform_create(self, serializer):
        carga = serializer.save(usuario=self.request.user)

        # Disparamos la tarea de Celery, enviándole el ID y el nombre del esquema (tenant)
        from .tasks import procesar_carga_masiva_task
        schema_name = self.request.tenant.schema_name

        transaction.on_commit(
            lambda: procesar_carga_masiva_task.delay(carga.id, schema_name)
        )

    @action(detail=True, methods=['get'])
    def descargar_errores(self, request, pk=None):
        """
        Genera un archivo 'Boomerang' al vuelo con los datos originales que fallaron
        y la explicación del error. Soporta formato ?formato=xlsx o ?formato=csv.
        """
        carga = self.get_object()
        errores = carga.detalle_errores or []
        formato = request.query_params.get('formato', 'xlsx').lower()

        if not errores:
            return HttpResponse("No hay errores para esta carga.", status=204)

        import pandas as pd
        import io

        # 1. Reconstruir cabeceras y datos dinámicamente
        datos_procesados = []

        # Para garantizar el orden, primero detectamos todas las cabeceras originales posibles
        cabeceras_extra = []
        for err in errores:
            datos = err.get('datos_originales', {})
            if isinstance(datos, dict):
                for key in datos.keys():
                    if key not in cabeceras_extra:
                        cabeceras_extra.append(key)

        # 2. Armar las filas
        for err in errores:
            fila_original = err.get('datos_originales', {})
            if not isinstance(fila_original, dict):
                fila_original = {}

            # Fila base con el diagnóstico
            fila_dict = {
                'MOTIVO_ERROR': err.get('error', 'Error desconocido'),
                'FILA_ORIGINAL': err.get('fila', '?')
            }
            # Agregar el resto de las columnas del usuario
            for col in cabeceras_extra:
                fila_dict[col] = fila_original.get(col, '')

            datos_procesados.append(fila_dict)

        # Convertimos a DataFrame de Pandas
        df = pd.DataFrame(datos_procesados)

        # 3. Exportación
        if formato == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="Errores_Importacion_{carga.pk}.csv"'
            response.write('\ufeff'.encode('utf8'))  # BOM para UTF-8
            df.to_csv(response, sep=';', index=False)
            return response

        else:  # Formato nativo Excel (XLSX)
            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="Errores_Importacion_{carga.pk}.xlsx"'

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Errores')

                # UX: Autoajustar el ancho de las columnas en el Excel
                worksheet = writer.sheets['Errores']
                for idx, col in enumerate(df.columns):
                    # Calcula el ancho máximo entre el título de la columna y su contenido
                    max_len = min(max(df[col].astype(str).map(len).max(), len(str(col))) + 2, 60)
                    worksheet.column_dimensions[chr(65 + idx)].width = max_len

            response.write(output.getvalue())
            return response

    @action(detail=False, methods=['get'])
    def descargar_plantilla(self, request):
        """
        Devuelve la plantilla con las cabeceras exactas.
        Soporta formato ?formato=xlsx o ?formato=csv.
        """
        entidad = request.query_params.get('entidad')
        formato = request.query_params.get('formato', 'xlsx').lower()

        if not entidad:
            return Response({"detail": "Debe especificar la entidad."}, status=400)

        # 1. CONTRATO MAESTRO DE DATOS
        plantillas = {
            'PRECIOS_COMPRA': ['*cuit_proveedor', '*codigo_articulo', '*precio', 'moneda_id', 'nombre_lista',
                               '*actualiza_costo'],
            'PRECIOS_VENTA': ['*codigo_articulo', '*precio', 'moneda_id', 'nombre_lista', 'cantidad_minima'],
            'CLIENTES': [
                '*cuit_o_dni', '*razon_social', '*situacion_iva', 'sexo', 'email', 'nombre_fantasia',
                'categoria', 'limite_credito', 'permite_cta_cte', 'dias_vencimiento', 'descuento_base',
                'zona', 'contacto_nombre', 'contacto_telefono', 'direccion', 'observaciones'
            ],
            'PROVEEDORES': [
                '*cuit_o_dni', '*razon_social', '*situacion_iva', 'sexo', 'email', 'nombre_fantasia',
                'limite_credito', 'plazo_pago_dias', 'descuento_compra', 'situacion_iibb', 'nro_iibb',
                'banco_nombre', 'banco_cbu', 'contacto_nombre', 'contacto_telefono', 'direccion', 'observaciones'
            ],
            'ARTICULOS': [
                '*codigo_articulo', 'ean', 'qr', '*descripcion', 'descripcion_larga', 'cod_fabricante',
                'marca', 'rubro', 'es_servicio', 'es_bien_de_uso', '*precio_costo', 'moneda_costo_id', 'utilidad',
                'moneda_venta_id',
                'impuestos_ids', 'unidad_medida_stock', 'unidad_medida_venta',
                'stock_minimo', 'stock_maximo', 'stock_seguridad', 'peso_kg',
                'alto_cm', 'ancho_cm', 'profundidad_cm', 'ubicacion', 'nota'
            ],
            'STOCK_INICIAL': ['*codigo_articulo', '*deposito_id', '*cantidad', 'observaciones']
        }

        cabeceras = plantillas.get(entidad)
        if not cabeceras:
            return Response({"detail": "Entidad no soportada para plantillas."}, status=400)

        instrucciones = ['[OBLIGATORIO]' if col.startswith('*') else '[OPCIONAL]' for col in cabeceras]

        # 2. DICCIONARIO DE EJEMPLOS CORREGIDO (Sintaxis dict: clave: valor)
        ejemplos = {
            'PRECIOS_COMPRA': ['30111111118', 'ART-001', '50.50', '2', 'Lista Principal', 'S'],
            'PRECIOS_VENTA': ['ART-001', '7500.00', '1', 'Lista Mayorista', '1'],
            'CLIENTES': ['20123456784', 'Juan Perez', '5', 'M', 'juan@email.com', 'Kiosco Juan', 'MIN', '100000', 'S',
                         '15', '5.5', 'Centro', 'Juan', '343555555', 'Calle Falsa 123', 'Entregar por la tarde'],
            'PROVEEDORES': ['30716844338', 'Proveedor SA', '1', 'J', 'ventas@proveedor.com', 'ProvSA', '500000', '30',
                            '10', 'Convenio', '901-123456', 'Banco Galicia', '0070000000000000000000', 'Carlos',
                            '1144445555', 'Av Principal 456', ''],
            'ARTICULOS': ['ART-001', '7791234567890', 'http://mi-erp.com/qr/1', 'Coca Cola 2.25L', 'Gaseosa', 'FAB-001',
                          'Coca Cola', 'Bebidas', 'N', 'N', '1.50', '2', '30.00', '1', '1,2', 'UN', 'UN', '10', '100',
                          '5', '2.25', '35', '10', '10', 'Pasillo 4', 'Frágil'],
            'STOCK_INICIAL': ['ART-001', '1', '150.5', 'Apertura de sistema']
        }

        fila_ejemplo = ejemplos.get(entidad, [])

        import pandas as pd
        import io

        # 3. CONSTRUCCIÓN DEL DATAFRAME
        data = [instrucciones]
        if fila_ejemplo:
            data.append(fila_ejemplo)

        df = pd.DataFrame(data, columns=cabeceras)

        # 4. EXPORTACIÓN OMNIFORMATO
        if formato == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="Plantilla_{entidad}.csv"'
            response.write('\ufeff'.encode('utf8'))  # BOM UTF-8
            df.to_csv(response, sep=';', index=False)
            return response

        else:  # Formato XLSX
            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="Plantilla_{entidad}.xlsx"'

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Datos a Importar')
                worksheet = writer.sheets['Datos a Importar']
                for idx, col in enumerate(df.columns):
                    max_len = min(max(df[col].astype(str).map(len).max() if not df.empty else 0, len(str(col))) + 2, 40)
                    worksheet.column_dimensions[chr(65 + idx)].width = max_len

            response.write(output.getvalue())
            return response


# ─────────────────────────────────────────────
#  UNIDADES DE MEDIDA (necesario para formulario de artículos)
# ─────────────────────────────────────────────

from rest_framework import serializers as drf_serializers


class UnidadMedidaSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = UnidadMedida
        fields = ['id', 'nombre', 'simbolo']


class UnidadMedidaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/unidades-medida/     — lista todas las unidades
    GET /api/unidades-medida/{id}/
    """
    queryset = UnidadMedida.objects.all().order_by('nombre')
    serializer_class = UnidadMedidaSerializer


class SerieDocumentoSerializer(drf_serializers.ModelSerializer):
    # Traemos campos útiles del Tipo de Comprobante relacionado para el Frontend
    tipo_comprobante_nombre = drf_serializers.CharField(source='tipo_comprobante.nombre', read_only=True)
    letra = drf_serializers.CharField(source='tipo_comprobante.letra', read_only=True)
    codigo_afip = drf_serializers.CharField(source='tipo_comprobante.codigo_afip', read_only=True)
    es_fiscal = drf_serializers.BooleanField(source='tipo_comprobante.es_fiscal', read_only=True)

    class Meta:
        model = SerieDocumento
        # FIX BUG: Eliminamos 'get_tipo_comprobante_display' (fallaba por ser ForeignKey)
        # Agregamos los nuevos campos de conveniencia para el Frontend
        fields = [
            'id',
            'nombre',
            'tipo_comprobante',
            'tipo_comprobante_nombre',
            'letra',
            'codigo_afip',
            'es_fiscal',
            'punto_venta',
            'ultimo_numero',
            'solicitar_cae_automaticamente',
            'es_manual',
            'activo',
            'deposito_defecto'
        ]


class SerieDocumentoViewSet(viewsets.ModelViewSet):
    """
    CRUD /api/series/ — series (talonarios) de comprobantes
    Soporta filtros por query params: ?clase=V&activo=true
    """
    serializer_class = SerieDocumentoSerializer

    def get_queryset(self):
        qs = SerieDocumento.objects.select_related('tipo_comprobante').all().order_by('nombre')

        # 🔒 FILTRO DE SEGURIDAD: Solo devolver series donde el usuario esté autorizado
        # (Los superusuarios pueden ver todas para poder administrar)
        if self.request.user and not self.request.user.is_superuser:
            qs = qs.filter(usuarios_autorizados=self.request.user)

        activo = self.request.query_params.get('activo')
        if activo is not None:
            qs = qs.filter(activo=(activo.lower() == 'true'))

        clase = self.request.query_params.get('clase')
        if clase:
            qs = qs.filter(tipo_comprobante__clase=clase)

        # El .distinct() es importante cuando usamos filtros ManyToMany para evitar duplicados
        return qs.distinct()


class ReglaConversionViewSet(viewsets.ModelViewSet):
    queryset = ReglaConversionComprobante.objects.select_related(
        'tipo_origen', 'tipo_destino'
    ).order_by('orden', 'tipo_origen__nombre')
    serializer_class = ReglaConversionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        origen = self.request.query_params.get('tipo_origen')
        if origen:
            qs = qs.filter(tipo_origen_id=origen, activo=True)
        activo = self.request.query_params.get('activo')
        if activo is not None:
            qs = qs.filter(activo=activo.lower() in ('true', '1', 'yes'))
        return qs