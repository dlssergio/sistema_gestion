# parametros/importers/base.py
import unicodedata
import pandas as pd
import io
from django.db import transaction
from parametros.models import CargaMasiva


class BaseImporter:
    """
    Clase Maestra (Template Method) para todas las importaciones masivas.
    Maneja la lectura de CSV, auto-detección de delimitadores, limpieza de cabeceras,
    y actualización segura de la barra de progreso en la base de datos.
    """

    def __init__(self, carga_id):
        self.carga = CargaMasiva.objects.get(id=carga_id)
        self.errores = []
        self.filas_exitosas = 0
        self.filas_error = 0
        self.modo = self.carga.modo

    def procesar(self):
        try:
            archivo = self.carga.archivo
            ext = archivo.name.split('.')[-1].lower()

            # Leer el contenido en bruto (Binario)
            archivo.open(mode='rb')
            file_content = archivo.read()

            # 1. LECTURA INTELIGENTE OMNIFORMATO
            try:
                if ext == 'csv':
                    # Decodificación resiliente: Intentamos UTF-8 con BOM (Excel), si falla usamos Latin1
                    try:
                        text_content = file_content.decode('utf-8-sig')
                    except UnicodeDecodeError:
                        text_content = file_content.decode('latin1')

                    # Pasamos el texto limpio a Pandas a través de StringIO
                    text_stream = io.StringIO(text_content)
                    df = pd.read_csv(text_stream, sep=None, engine='python', dtype=str, keep_default_na=False)

                elif ext in ['xls', 'xlsx']:
                    # Excel nativo necesita flujo binario
                    binary_stream = io.BytesIO(file_content)
                    df = pd.read_excel(binary_stream, dtype=str, keep_default_na=False)
                else:
                    raise ValueError(f"Formato .{ext} no soportado. Usa CSV, XLS o XLSX.")

            except Exception as e:
                raise ValueError(
                    f"Error al leer el archivo. Asegúrate de que el formato sea correcto. Detalle: {str(e)}")

            # Limpiamos filas completamente vacías
            df = df.dropna(how='all')
            total_filas = len(df)

            self.carga.total_filas = total_filas
            self.carga.save(update_fields=['total_filas'])

            if total_filas == 0:
                self._finalizar(CargaMasiva.Estado.ERROR,
                                [{"fila": 0, "error": "El archivo está vacío o es ilegible.", "datos_originales": {}}])
                return

            # 2. NORMALIZACIÓN DE CABECERAS
            # Convertimos "Precio de Costo*" a "precio_de_costo"
            columnas_crudas = df.columns.tolist()
            columnas_limpias = [
                unicodedata.normalize('NFKD', str(col)).encode('ASCII', 'ignore').decode(
                    'utf-8').strip().lower().replace(' ', '_').replace('*', '')
                for col in columnas_crudas
            ]
            df.columns = columnas_limpias

            # Convertimos el DataFrame a una lista de diccionarios (Compatible con todo tu código anterior)
            registros = df.to_dict(orient='records')

            # 3. PRE-PROCESAMIENTO (Validación de contrato por las clases hijas)
            self.pre_procesar(columnas_limpias)

            # 4. TRANSACCIÓN ATÓMICA
            with transaction.atomic():
                for index, fila in enumerate(registros):
                    # Fila Excel real (Index + 2, por la cabecera)
                    num_fila = index + 2
                    try:
                        self.procesar_fila(fila, num_fila)
                        self.filas_exitosas += 1
                    except Exception as e:
                        self.errores.append({
                            'fila': num_fila,
                            'error': str(e),
                            'datos_originales': fila
                        })
                        self.filas_error += 1

                    # Telemetría en tiempo real
                    if (index + 1) % 100 == 0:
                        self.carga.filas_procesadas = index + 1
                        self.carga.save(update_fields=['filas_procesadas'])

                self.post_procesar()

            estado_final = CargaMasiva.Estado.COMPLETADO if self.filas_exitosas > 0 else CargaMasiva.Estado.ERROR
            self._finalizar(estado_final)

        except Exception as e:
            self.errores.append({'fila': 'CRÍTICO / Preparación', 'error': str(e), 'datos_originales': {}})
            self._finalizar(CargaMasiva.Estado.ERROR)

    def _finalizar(self, estado, errores_extra=None):
        if errores_extra:
            self.errores.extend(errores_extra)
        self.carga.filas_procesadas = self.carga.total_filas
        self.carga.filas_exitosas = self.filas_exitosas
        self.carga.filas_error = self.filas_error
        self.carga.detalle_errores = self.errores
        self.carga.estado = estado
        self.carga.save()

    def pre_procesar(self, columnas):
        pass

    def procesar_fila(self, fila, num_fila):
        raise NotImplementedError()

    def post_procesar(self):
        pass