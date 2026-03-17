import csv
import io
import unicodedata
from celery import shared_task
from django.db import transaction
from django_tenants.utils import schema_context
from parametros.models import CargaMasiva


@shared_task
def procesar_carga_masiva_task(carga_id, schema_name):  # <--- Recibe schema_name
    """
    Tarea asíncrona principal compatible con Multi-Tenant.
    """
    # Entramos al esquema del cliente correspondiente antes de hacer nada
    with schema_context(schema_name):
        try:
            carga = CargaMasiva.objects.get(id=carga_id)
        except CargaMasiva.DoesNotExist:
            print(f"❌ Error: CargaMasiva {carga_id} no encontrada en esquema {schema_name}")
            return False

        carga.estado = CargaMasiva.Estado.PROCESANDO
        carga.save(update_fields=['estado'])

        try:
            if carga.entidad == CargaMasiva.Entidad.ARTICULOS:
                procesar_articulos(carga)
            elif carga.entidad == CargaMasiva.Entidad.PROVEEDORES:
                pass
            elif carga.entidad == CargaMasiva.Entidad.CLIENTES:
                pass
            else:
                raise ValueError(f"Entidad '{carga.entidad}' no soportada.")

        except Exception as e:
            carga.estado = CargaMasiva.Estado.ERROR
            carga.detalle_errores = [{"fila": "General", "error": str(e)}]
            carga.save(update_fields=['estado', 'detalle_errores'])
            return False

        return True


def procesar_articulos(carga):
    from inventario.models import Articulo, Rubro
    from parametros.models import UnidadMedida
    import csv  # Asegúrate de que esté importado arriba en el archivo

    errores = []
    objetos_a_crear = []
    filas_exitosas = 0
    filas_error = 0

    archivo = carga.archivo
    archivo.open(mode='rb')
    decoded_file = archivo.read().decode('utf-8').splitlines()

    total_filas = len(decoded_file) - 1 if len(decoded_file) > 0 else 0
    carga.total_filas = total_filas
    carga.save(update_fields=['total_filas'])

    if total_filas == 0:
        return  # Si el archivo está vacío, no hacemos nada

    # --- MAGIA: Auto-detectar si es coma (,) o punto y coma (;) ---
    try:
        dialect = csv.Sniffer().sniff(decoded_file[0], delimiters=[',', ';', '\t'])
        reader = csv.DictReader(decoded_file, dialect=dialect)
    except csv.Error:
        # Si falla la detección, asumimos coma por defecto
        reader = csv.DictReader(decoded_file)

    # Limpiar los nombres de las columnas (pasar a minúsculas y quitar espacios/tildes)
    import unicodedata
    def limpiar_texto(texto):
        texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
        return texto.strip().lower()

    if reader.fieldnames:
        reader.fieldnames = [limpiar_texto(col) for col in reader.fieldnames]

    # Valores por defecto
    rubro_default = Rubro.objects.first()
    if not rubro_default:
        rubro_default = Rubro.objects.create(nombre="General")

    unidad_default = UnidadMedida.objects.first()

    codigos_existentes = set(Articulo.objects.values_list('cod_articulo', flat=True))

    for index, fila in enumerate(reader):
        try:
            # Ahora busca "codigo" y "descripcion" sin importar si en el Excel decia "Código"
            codigo = fila.get('codigo', '').strip()
            descripcion = fila.get('descripcion', '').strip()

            if not codigo or not descripcion:
                raise ValueError("Falta el 'codigo' o la 'descripcion' en esta fila.")

            if codigo in codigos_existentes:
                raise ValueError(f"El código '{codigo}' ya existe en el sistema.")

            articulo = Articulo(
                cod_articulo=codigo,
                descripcion=descripcion,
                rubro=rubro_default,
                unidad_medida_stock=unidad_default,
                unidad_medida_venta=unidad_default,
            )

            objetos_a_crear.append(articulo)
            codigos_existentes.add(codigo)
            filas_exitosas += 1

        except Exception as e:
            errores.append({'fila': index + 2, 'error': str(e)})
            filas_error += 1

        if (index + 1) % 100 == 0:
            carga.filas_procesadas = index + 1
            carga.save(update_fields=['filas_procesadas'])

    # Guardado en base de datos
    if objetos_a_crear:
        with transaction.atomic():
            Articulo.objects.bulk_create(objetos_a_crear, batch_size=500)

    carga.filas_procesadas = total_filas
    carga.filas_exitosas = filas_exitosas
    carga.filas_error = filas_error
    carga.detalle_errores = errores
    carga.estado = CargaMasiva.Estado.COMPLETADO
    carga.save()


# --- NUEVO MOTOR: PROVEEDORES ---
def procesar_proveedores(carga):
    from entidades.models import Entidad, SituacionIVA
    from compras.models import Proveedor

    errores, objetos_entidad_crear, objetos_entidad_actualizar = [], [], []
    objetos_proveedor_crear, objetos_proveedor_actualizar = [], []
    filas_exitosas, filas_error = 0, 0

    archivo = carga.archivo
    archivo.open(mode='rb')
    decoded_file = archivo.read().decode('utf-8').splitlines()

    total_filas = len(decoded_file) - 1 if len(decoded_file) > 0 else 0
    carga.total_filas = total_filas
    carga.save(update_fields=['total_filas'])
    if total_filas == 0: return

    try:
        dialect = csv.Sniffer().sniff(decoded_file[0], delimiters=[',', ';', '\t'])
        reader = csv.DictReader(decoded_file, dialect=dialect)
    except csv.Error:
        reader = csv.DictReader(decoded_file)

    def limpiar_texto(texto):
        return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').strip().lower()

    if reader.fieldnames:
        reader.fieldnames = [limpiar_texto(col) for col in reader.fieldnames]

    # Pre-cargas en memoria para validación ultra-rápida
    situacion_iva_default = SituacionIVA.objects.first()
    if not situacion_iva_default:
        raise ValueError("Debe existir al menos una Situación de IVA en el sistema antes de importar.")

    entidades_db = Entidad.objects.in_bulk(field_name='cuit')  # Buscamos por CUIT
    proveedores_db = {p.entidad_id: p for p in Proveedor.objects.all()}  # Buscamos por ID de Entidad

    columnas_entidad = [col for col in reader.fieldnames if hasattr(Entidad, col) and col != 'cuit']
    columnas_proveedor = [col for col in reader.fieldnames if hasattr(Proveedor, col) and col != 'entidad']

    for index, fila in enumerate(reader):
        try:
            cuit_crudo = fila.get('cuit', '').strip()
            razon_social = fila.get('razon_social', '').strip()

            if not cuit_crudo or not razon_social:
                raise ValueError("Las columnas 'cuit' y 'razon_social' son obligatorias.")

            cuit = cuit_crudo.replace("-", "")

            # 1. TRABAJAR LA ENTIDAD BASE
            existe_entidad = cuit in entidades_db

            if carga.modo == carga.Modo.CREAR and existe_entidad:
                raise ValueError(f"El CUIT '{cuit}' ya existe.")
            if carga.modo == carga.Modo.ACTUALIZAR and not existe_entidad:
                raise ValueError(f"El CUIT '{cuit}' no existe.")

            if existe_entidad:
                entidad = entidades_db[cuit]
                for campo in columnas_entidad:
                    val = fila.get(campo)
                    if val is not None and str(val).strip() != "":
                        setattr(entidad, campo, str(val).strip())
                objetos_entidad_actualizar.append(entidad)
            else:
                entidad = Entidad(cuit=cuit, razon_social=razon_social, situacion_iva=situacion_iva_default)
                for campo in columnas_entidad:
                    val = fila.get(campo)
                    if val and str(val).strip() != "" and campo != 'razon_social':
                        setattr(entidad, campo, str(val).strip())
                objetos_entidad_crear.append(entidad)
                entidades_db[cuit] = entidad  # La guardamos temporalmente en el dict

            # 2. TRABAJAR EL PERFIL DE PROVEEDOR
            # Nota: Si acabamos de instanciar la Entidad, no tiene ID todavía.
            # Bulk_create con OneToOne no soporta asignar objetos sin PK guardados.
            # Para simplificar y evitar fallos de integridad, si la entidad es nueva, la guardamos individualmente aquí.
            if not entidad.pk:
                entidad.save()

            existe_proveedor = entidad.pk in proveedores_db

            if existe_proveedor:
                proveedor = proveedores_db[entidad.pk]
                hubo_cambios = False
                for campo in columnas_proveedor:
                    val = fila.get(campo)
                    if val is not None and str(val).strip() != "":
                        setattr(proveedor, campo, str(val).strip())
                        hubo_cambios = True
                if hubo_cambios: objetos_proveedor_actualizar.append(proveedor)
            else:
                nuevo_prov = Proveedor(entidad=entidad)
                for campo in columnas_proveedor:
                    val = fila.get(campo)
                    if val and str(val).strip() != "":
                        setattr(nuevo_prov, campo, str(val).strip())
                objetos_proveedor_crear.append(nuevo_prov)
                proveedores_db[entidad.pk] = nuevo_prov

            filas_exitosas += 1
        except Exception as e:
            errores.append({'fila': index + 2, 'error': str(e)})
            filas_error += 1

        if (index + 1) % 100 == 0:
            carga.filas_procesadas = index + 1
            carga.save(update_fields=['filas_procesadas'])

    try:
        with transaction.atomic():
            if objetos_entidad_actualizar and columnas_entidad:
                Entidad.objects.bulk_update(objetos_entidad_actualizar, columnas_entidad, batch_size=500)

            if objetos_proveedor_crear:
                Proveedor.objects.bulk_create(objetos_proveedor_crear, batch_size=500)

            if objetos_proveedor_actualizar and columnas_proveedor:
                Proveedor.objects.bulk_update(objetos_proveedor_actualizar, columnas_proveedor, batch_size=500)
    except Exception as db_error:
        errores.append({'fila': 'Guardado Masivo', 'error': str(db_error)})
        filas_error += len(objetos_proveedor_crear) + len(objetos_proveedor_actualizar)
        filas_exitosas = 0  # Asumimos que la transacción completa falló
        carga.estado = CargaMasiva.Estado.ERROR
    else:
        # Si todo el guardado SQL fue bien, completamos
        carga.estado = CargaMasiva.Estado.COMPLETADO
        carga.filas_exitosas = filas_exitosas

    carga.filas_procesadas = total_filas
    carga.filas_error = filas_error
    carga.detalle_errores = errores
    carga.save()


# --- NUEVO MOTOR: CLIENTES ---
def procesar_clientes(carga):
    from entidades.models import Entidad, SituacionIVA
    from ventas.models import Cliente

    errores, objetos_entidad_crear, objetos_entidad_actualizar = [], [], []
    objetos_cliente_crear, objetos_cliente_actualizar = [], []
    filas_exitosas, filas_error = 0, 0

    archivo = carga.archivo
    archivo.open(mode='rb')
    decoded_file = archivo.read().decode('utf-8').splitlines()

    total_filas = len(decoded_file) - 1 if len(decoded_file) > 0 else 0
    carga.total_filas = total_filas
    carga.save(update_fields=['total_filas'])
    if total_filas == 0: return

    try:
        dialect = csv.Sniffer().sniff(decoded_file[0], delimiters=[',', ';', '\t'])
        reader = csv.DictReader(decoded_file, dialect=dialect)
    except csv.Error:
        reader = csv.DictReader(decoded_file)

    def limpiar_texto(texto):
        return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').strip().lower()

    if reader.fieldnames:
        reader.fieldnames = [limpiar_texto(col) for col in reader.fieldnames]

    situacion_iva_default = SituacionIVA.objects.first()
    if not situacion_iva_default:
        raise ValueError("Debe existir al menos una Situación de IVA en el sistema antes de importar.")

    entidades_db = Entidad.objects.in_bulk(field_name='cuit')
    clientes_db = {c.entidad_id: c for c in Cliente.objects.all()}

    columnas_entidad = [col for col in reader.fieldnames if hasattr(Entidad, col) and col != 'cuit']
    columnas_cliente = [col for col in reader.fieldnames if hasattr(Cliente, col) and col != 'entidad']

    for index, fila in enumerate(reader):
        try:
            cuit_crudo = fila.get('cuit', '').strip()
            razon_social = fila.get('razon_social', '').strip()

            if not cuit_crudo or not razon_social:
                raise ValueError("Las columnas 'cuit' y 'razon_social' son obligatorias.")

            cuit = cuit_crudo.replace("-", "")
            existe_entidad = cuit in entidades_db

            if carga.modo == carga.Modo.CREAR and existe_entidad:
                raise ValueError(f"El CUIT '{cuit}' ya existe.")
            if carga.modo == carga.Modo.ACTUALIZAR and not existe_entidad:
                raise ValueError(f"El CUIT '{cuit}' no existe.")

            if existe_entidad:
                entidad = entidades_db[cuit]
                for campo in columnas_entidad:
                    val = fila.get(campo)
                    if val is not None and str(val).strip() != "":
                        setattr(entidad, campo, str(val).strip())
                objetos_entidad_actualizar.append(entidad)
            else:
                entidad = Entidad(cuit=cuit, razon_social=razon_social, situacion_iva=situacion_iva_default)
                for campo in columnas_entidad:
                    val = fila.get(campo)
                    if val and str(val).strip() != "" and campo != 'razon_social':
                        setattr(entidad, campo, str(val).strip())
                objetos_entidad_crear.append(entidad)
                entidades_db[cuit] = entidad

            if not entidad.pk:
                entidad.save()

            existe_cliente = entidad.pk in clientes_db

            if existe_cliente:
                cliente = clientes_db[entidad.pk]
                hubo_cambios = False
                for campo in columnas_cliente:
                    val = fila.get(campo)
                    if val is not None and str(val).strip() != "":
                        setattr(cliente, campo, str(val).strip())
                        hubo_cambios = True
                if hubo_cambios: objetos_cliente_actualizar.append(cliente)
            else:
                nuevo_cli = Cliente(entidad=entidad)
                for campo in columnas_cliente:
                    val = fila.get(campo)
                    if val and str(val).strip() != "":
                        setattr(nuevo_cli, campo, str(val).strip())
                objetos_cliente_crear.append(nuevo_cli)
                clientes_db[entidad.pk] = nuevo_cli

            filas_exitosas += 1
        except Exception as e:
            errores.append({'fila': index + 2, 'error': str(e)})
            filas_error += 1

        if (index + 1) % 100 == 0:
            carga.filas_procesadas = index + 1
            carga.save(update_fields=['filas_procesadas'])

    try:
        with transaction.atomic():
            if objetos_entidad_actualizar and columnas_entidad:
                Entidad.objects.bulk_update(objetos_entidad_actualizar, columnas_entidad, batch_size=500)
            if objetos_cliente_crear:
                Cliente.objects.bulk_create(objetos_cliente_crear, batch_size=500)
            if objetos_cliente_actualizar and columnas_cliente:
                Cliente.objects.bulk_update(objetos_cliente_actualizar, columnas_cliente, batch_size=500)
    except Exception as db_error:
        errores.append({'fila': 'Guardado Masivo', 'error': str(db_error)})
        filas_error += len(objetos_cliente_crear) + len(objetos_cliente_actualizar)
        filas_exitosas = 0
        carga.estado = CargaMasiva.Estado.ERROR
    else:
        carga.estado = CargaMasiva.Estado.COMPLETADO
        carga.filas_exitosas = filas_exitosas

    carga.filas_procesadas = total_filas
    carga.filas_error = filas_error
    carga.detalle_errores = errores
    carga.save()