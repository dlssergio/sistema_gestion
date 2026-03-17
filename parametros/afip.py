# parametros/afip.py
import os
import sys
import shutil
import requests
import ssl
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# Librerías AFIP
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1
# Modelos
from .models import AfipCertificado, AfipToken, ConfiguracionEmpresa

# Logs para verificar el XML
logging.basicConfig(level=logging.INFO)
logging.getLogger('zeep.transports').setLevel(logging.DEBUG)
logging.getLogger('pysimplesoap.client').setLevel(logging.DEBUG)


class SSLContextAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context(ciphers='DEFAULT:@SECLEVEL=1')
        kwargs['ssl_context'] = context
        return super(SSLContextAdapter, self).init_poolmanager(*args, **kwargs)


class AfipManager:
    def __init__(self):
        self._configurar_openssl()

        self.cache_dir = os.path.join(settings.BASE_DIR, 'afip_cache')
        os.makedirs(self.cache_dir, exist_ok=True)

        config = ConfiguracionEmpresa.objects.first()
        if not config or not config.usar_factura_electronica:
            raise Exception("Facturación Electrónica desactivada.")

        self.certificado_db = AfipCertificado.objects.filter(activo=True).first()
        local_crt = r"C:\certificadoElectronico\certificado.crt"
        local_key = r"C:\certificadoElectronico\privada.key"

        if os.path.exists(local_crt) and os.path.exists(local_key):
            self.cert_path = local_crt
            self.key_path = local_key
            if self.certificado_db:
                self.cuit = config.entidad.cuit
                self.produccion = self.certificado_db.es_produccion
            else:
                self.cuit = config.entidad.cuit
                self.produccion = False
        elif self.certificado_db:
            self.cuit = self.certificado_db.cuit
            self.produccion = self.certificado_db.es_produccion
            try:
                self.cert_path = self.certificado_db.certificado.path
                self.key_path = self.certificado_db.clave_privada.path
            except:
                raise Exception("Error accediendo a certificados.")
        else:
            raise Exception("No se encontraron certificados.")

    def _configurar_openssl(self):
        rutas = [r"C:\OpenSSL-Win64\bin\openssl.exe", r"C:\OpenSSL\bin\openssl.exe",
                 r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe"]
        openssl_bin = "openssl"
        found = False
        for r in rutas:
            if os.path.exists(r):
                openssl_bin = r
                found = True
                break

        safe_bin = f'"{openssl_bin}"' if " " in openssl_bin and not openssl_bin.startswith('"') else openssl_bin
        WSAA.OPENSSL = safe_bin
        WSFEv1.OPENSSL = safe_bin
        if found: os.environ['PATH'] += os.pathsep + os.path.dirname(openssl_bin.strip('"'))

    def _preparar_wsdl_hibrido(self):
        url_origen = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"
        archivo_destino = os.path.join(self.cache_dir, "wsfev1_hibrido.wsdl")
        url_endpoint_prod = "https://servicios1.afip.gov.ar/wsfev1/service.asmx"
        url_endpoint_homo = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx"

        try:
            session = requests.Session()
            session.mount('https://', SSLContextAdapter())
            if not os.path.exists(archivo_destino):
                resp = session.get(url_origen, timeout=15)
                if resp.status_code != 200: raise Exception(f"Status {resp.status_code}")
                contenido_wsdl = resp.text
                if not self.produccion:
                    contenido_wsdl = contenido_wsdl.replace(url_endpoint_prod, url_endpoint_homo)
                with open(archivo_destino, 'w', encoding='utf-8') as f:
                    f.write(contenido_wsdl)
            return archivo_destino
        except Exception as e:
            return url_endpoint_prod if self.produccion else url_endpoint_homo + "?WSDL"

    def _autenticar(self, service="wsfe"):
        if self.certificado_db:
            token_obj = AfipToken.objects.filter(certificado=self.certificado_db, service=service,
                                                 expira__gt=timezone.now()).first()
            if token_obj: return token_obj.token, token_obj.sign

        wsaa = WSAA()
        url = "https://wsaa.afip.gov.ar/ws/services/LoginCms" if self.produccion else "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"

        tra = wsaa.CreateTRA(service=service, ttl=36000)
        cms = wsaa.SignTRA(tra, self.cert_path, self.key_path)
        wsaa.Conectar(None, url)
        if not wsaa.LoginCMS(cms): raise Exception(f"Error WSAA: {wsaa.Excepcion}")

        if self.certificado_db:
            AfipToken.objects.create(
                certificado=self.certificado_db, service=service, unique_id=getattr(wsaa, 'Id', '0'),
                token=wsaa.Token, sign=wsaa.Sign, expira=timezone.now() + timedelta(hours=11)
            )
        return wsaa.Token, wsaa.Sign

    def _conectar_wsfe(self):
        token, sign = self._autenticar("wsfe")
        wsfe = WSFEv1()
        wsfe.Cuit = self.cuit
        wsfe.Token = token
        wsfe.Sign = sign
        wsdl_path = self._preparar_wsdl_hibrido()
        wsfe.Conectar(cache=self.cache_dir, wsdl=wsdl_path)
        return wsfe

    def obtener_ultimo_numero(self, tipo_cbte, pto_vta):
        try:
            wsfe = self._conectar_wsfe()
            auth = {'Token': wsfe.Token, 'Sign': wsfe.Sign, 'Cuit': wsfe.Cuit}
            response = wsfe.client.FECompUltimoAutorizado(Auth=auth, PtoVta=pto_vta, CbteTipo=tipo_cbte)
            resultado = 0
            if isinstance(response, dict):
                if 'FECompUltimoAutorizadoResult' in response:
                    resultado = response['FECompUltimoAutorizadoResult'].get('CbteNro', 0)
                else:
                    resultado = response.get('CbteNro', 0)
            else:
                if hasattr(response, 'FECompUltimoAutorizadoResult'):
                    resultado = response.FECompUltimoAutorizadoResult.CbteNro
                else:
                    resultado = getattr(response, 'CbteNro', 0)
            return int(resultado)
        except Exception:
            return -1

    # --- NUEVO MÉTODO AGREGADO: CONSULTA DE EXISTENCIA ---
    def consultar_comprobante(self, tipo_cbte, pto_vta, nro_cbte):
        """
        Consulta a AFIP si un comprobante específico ya existe y devuelve sus datos.
        """
        try:
            wsfe = self._conectar_wsfe()
            auth = {'Token': wsfe.Token, 'Sign': wsfe.Sign, 'Cuit': wsfe.Cuit}
            cmp_consulta = {'CbteTipo': tipo_cbte, 'PtoVta': pto_vta, 'CbteNro': nro_cbte}

            response = wsfe.client.FECompConsultar(Auth=auth, FeCompConsReq=cmp_consulta)

            result = None
            if hasattr(response, 'FECompConsultarResult'):
                result = response.FECompConsultarResult
            elif isinstance(response, dict) and 'FECompConsultarResult' in response:
                result = response['FECompConsultarResult']

            if result and 'ResultGet' in result:
                datos = result['ResultGet']
                if 'CodAutorizacion' in datos and datos['CodAutorizacion']:
                    return {
                        'cae': datos['CodAutorizacion'],
                        'vto': datos['FchVto'],
                        'resultado': datos.get('Resultado', 'A')
                    }
            return None
        except Exception as e:
            print(f"⚠️ Error consultando AFIP: {e}")
            return None

    # -----------------------------------------------------

    def consultar_estado_servicio(self):
        status = {}
        try:
            wsfe = self._conectar_wsfe()
            wsfe.Dummy()
            status['online'] = True
            status['modo'] = 'PRODUCCIÓN' if self.produccion else 'HOMOLOGACIÓN'
            status['app_server'] = getattr(wsfe, 'AppServerStatus', 'OK')
            status['db_server'] = getattr(wsfe, 'DbServerStatus', 'OK')
            status['auth_server'] = getattr(wsfe, 'AuthServerStatus', 'OK')
        except Exception as e:
            return {'online': False, 'error': str(e)}

        codigos = [
            (1, "Factura A"), (6, "Factura B"), (11, "Factura C"),
            (2, "Nota Débito A"), (7, "Nota Débito B"), (12, "Nota Débito C"),
            (3, "Nota Crédito A"), (8, "Nota Crédito B"), (13, "Nota Crédito C")
        ]

        pto_vta = 1
        try:
            config = ConfiguracionEmpresa.objects.first()
            if config and config.punto_venta_afip: pto_vta = config.punto_venta_afip
        except:
            pass

        lista_info = []
        for cod, nombre in codigos:
            ultimo = self.obtener_ultimo_numero(cod, pto_vta)
            if ultimo >= 0:
                lista_info.append({'tipo': nombre, 'pv': pto_vta, 'ultimo': ultimo})

        status['numeracion'] = lista_info
        return status

    # --- EMISIÓN DE COMPROBANTE ---
    def emitir_comprobante(self, comprobante):
        if not comprobante.es_electronica(): return False

        print(f"\n🚀 PROCESANDO COMPROBANTE #{comprobante.numero} (MULTI-ORIGEN + SAFE)")

        # 1. RECUPERACIÓN DE FALLOS (Blindaje)
        tipo_cbte = int(comprobante.tipo_comprobante.codigo_afip)
        pto_vta = int(comprobante.punto_venta)
        numero = int(comprobante.numero)

        datos_existentes = self.consultar_comprobante(tipo_cbte, pto_vta, numero)
        if datos_existentes:
            print(f"♻️ RECUPERADO: El comprobante {numero} ya existía en AFIP. Asignando CAE...")
            comprobante.cae = datos_existentes['cae']
            try:
                comprobante.vto_cae = datetime.strptime(datos_existentes['vto'], '%Y%m%d').date()
            except:
                pass
            comprobante.afip_resultado = datos_existentes['resultado']
            comprobante.afip_error = None
            comprobante.afip_observaciones = "Comprobante recuperado automáticamente."
            # FIX RECURSION: Usamos update_fields
            comprobante.save(update_fields=['cae', 'vto_cae', 'afip_resultado', 'afip_error', 'afip_observaciones'])
            return True

        def get_val(obj):
            val = 0.0
            if obj is None:
                val = 0.0
            elif hasattr(obj, 'amount'):
                val = float(obj.amount)
            else:
                val = float(obj)
            return round(val, 2)

        wsfe = self._conectar_wsfe()

        try:
            ultimo = self.obtener_ultimo_numero(tipo_cbte, pto_vta)
            if ultimo == -1: raise Exception("Error conectando a AFIP.")

            # Validación de secuencia estricta
            if numero <= ultimo:
                raise Exception(f"Desincronización: Sistema intenta {numero}, AFIP ya tiene {ultimo}.")
            if numero != (ultimo + 1):
                raise Exception(f"Error Numeración: Sistema intenta {numero}, AFIP espera {ultimo + 1}")
        except Exception as e:
            comprobante.afip_error = str(e)
            # FIX RECURSION
            comprobante.save(update_fields=['afip_error'])
            raise Exception(str(e))

        entidad = comprobante.cliente.entidad
        doc_tipo, doc_nro = 99, 0
        total = get_val(comprobante.total)

        # ── Override para cliente genérico (C00000) ──────────────────────────
        # Si el comprobante tiene datos de cliente ocasional, los usamos en
        # lugar de los datos del cliente genérico para la solicitud de CAE.
        CODIGO_CLIENTE_GENERICO = 'C00000'
        es_cliente_generico = (
                comprobante.cliente.codigo_cliente == CODIGO_CLIENTE_GENERICO
        )

        # CUIT efectivo: override si existe, si no el de la entidad
        cuit_efectivo = (
            comprobante.cliente_cuit_override
            if es_cliente_generico and comprobante.cliente_cuit_override
            else entidad.cuit
        )

        # Limpiar guiones del CUIT para conversión a int
        def _parse_cuit(raw):
            if not raw:
                return None
            cleaned = str(raw).replace('-', '').replace(' ', '')
            return int(cleaned) if cleaned.isdigit() else None

        if comprobante.letra == 'A':
            # Factura A: SIEMPRE requiere CUIT (DocTipo=80)
            cuit_int = _parse_cuit(cuit_efectivo)
            if not cuit_int:
                raise Exception(
                    "Factura A requiere CUIT válido del receptor. "
                    "Ingresá el CUIT del cliente en el campo de datos del cliente."
                )
            doc_tipo, doc_nro = 80, cuit_int
        elif cuit_efectivo and total >= 100000:
            # Factura B/C: si hay CUIT y el total supera el umbral, informar CUIT
            cuit_int = _parse_cuit(cuit_efectivo)
            if cuit_int:
                doc_tipo, doc_nro = 80, cuit_int
        # else: doc_tipo=99, doc_nro=0 → Consumidor Final

        neto = get_val(comprobante.subtotal)
        iva = round(total - neto, 2)

        es_monotributo = tipo_cbte in [11, 12, 13]
        if es_monotributo:
            neto = total
            iva = 0.0

        id_iva_receptor = 5
        if hasattr(entidad, 'situacion_iva'):
            id_iva_receptor = int(entidad.situacion_iva.codigo_afip)

        # 1. DICCIONARIO BASE
        detalle_factura = {
            'Concepto': 1,
            'DocTipo': doc_tipo,
            'DocNro': doc_nro,
            'CbteDesde': comprobante.numero,
            'CbteHasta': comprobante.numero,
            'CbteFch': comprobante.fecha.strftime('%Y%m%d'),
            'ImpTotal': total,
            'ImpTotConc': 0,
            'ImpNeto': neto,
            'ImpOpEx': 0,
            'ImpTrib': 0,
            'ImpIVA': iva,
            'MonId': 'PES',
            'MonCotiz': 1,
            'CondicionIVAReceptorId': id_iva_receptor
        }

        # --- 2. LÓGICA DE ASOCIADOS MULTI-ORIGEN CON FILTRO INTELIGENTE ---
        lista_cbtes_asoc = []

        cuit_emisor = 0
        try:
            cuit_emisor = int(float(str(wsfe.Cuit).replace("-", "")))
        except:
            pass

        def fmt_fecha(dt):
            return dt.strftime('%Y%m%d') if dt else comprobante.fecha.strftime('%Y%m%d')

        # A) Buscamos asociados en la base de datos (ManyToManyField)
        if hasattr(comprobante, 'comprobantes_asociados') and comprobante.comprobantes_asociados.exists():
            for asoc in comprobante.comprobantes_asociados.all():

                # VALIDACIÓN CRÍTICA: SOLO ENVIAMOS A AFIP SI EL ORIGEN ES FISCAL
                if not asoc.tipo_comprobante or not asoc.tipo_comprobante.codigo_afip:
                    print(f"⏩ Omitiendo asociado interno: {asoc} (No es fiscal)")
                    continue

                try:
                    item = {
                        'Tipo': int(asoc.tipo_comprobante.codigo_afip),
                        'PtoVta': int(asoc.punto_venta),
                        'Nro': int(asoc.numero),
                        'Cuit': cuit_emisor,
                        'CbteFch': fmt_fecha(asoc.fecha)
                    }
                    lista_cbtes_asoc.append(item)
                except (ValueError, TypeError):
                    print(f"⚠️ Error procesando asociado {asoc}: Datos AFIP inválidos.")
                    continue

        # B) Si no hay en DB, buscamos en referencia externa (Fallback manual)
        elif comprobante.referencia_externa:
            try:
                parts = comprobante.referencia_externa.split('-')
                if len(parts) == 2:
                    # Deducimos el tipo según la letra de la Nota actual
                    tipo = 1 if comprobante.letra == 'A' else (6 if comprobante.letra == 'B' else 11)
                    item = {
                        'Tipo': tipo,
                        'PtoVta': int(parts[0]),
                        'Nro': int(parts[1]),
                        'Cuit': cuit_emisor,
                        'CbteFch': fmt_fecha(None)
                    }
                    lista_cbtes_asoc.append(item)
            except:
                pass

        # === INSERCIÓN EN EL PAYLOAD ===
        if lista_cbtes_asoc:
            print(f"DEBUG: Asociando {len(lista_cbtes_asoc)} comprobantes FISCALES.")
            detalle_factura['CbtesAsoc'] = {'CbteAsoc': lista_cbtes_asoc}

        # 3. IVA
        if iva > 0 and not es_monotributo:
            detalle_factura['Iva'] = {'AlicIva': [{'Id': 5, 'BaseImp': neto, 'Importe': iva}]}

        # 4. ENVÍO
        request_payload = {
            'FeCabReq': {'CantReg': 1, 'PtoVta': pto_vta, 'CbteTipo': tipo_cbte},
            'FeDetReq': {'FECAEDetRequest': [detalle_factura]}
        }

        print(f"📦 PAYLOAD: {request_payload}")
        auth = {'Token': wsfe.Token, 'Sign': wsfe.Sign, 'Cuit': wsfe.Cuit}

        try:
            response = wsfe.client.FECAESolicitar(Auth=auth, FeCAEReq=request_payload)

            root_resp = response
            if isinstance(response, dict) and 'FECAESolicitarResult' in response:
                root_resp = response['FECAESolicitarResult']

            if isinstance(root_resp, dict) and 'FeCabResp' in root_resp:
                if root_resp['FeCabResp']['Resultado'] == 'R' and 'Errors' in root_resp:
                    errs = root_resp['Errors']
                    msg = str(errs)
                    if isinstance(errs, dict) and 'Err' in errs:
                        msg = errs['Err']['Msg']
                    elif isinstance(errs, list):
                        msg = " | ".join([e['Msg'] for e in errs if 'Msg' in e])

                    comprobante.afip_error = f"Rechazo: {msg}"
                    # FIX RECURSION
                    comprobante.save(update_fields=['afip_error'])
                    raise Exception(f"Rechazo AFIP: {msg}")

            if 'FeDetResp' not in root_resp: raise Exception(f"Respuesta inesperada: {root_resp}")

            detalles = root_resp['FeDetResp']
            item = None
            if isinstance(detalles, dict) and 'FECAEDetResponse' in detalles:
                item = detalles['FECAEDetResponse']
            elif isinstance(detalles, list):
                item = detalles[0]
                if 'FECAEDetResponse' in item: item = item['FECAEDetResponse']
            else:
                item = detalles

            if item['Resultado'] == "A":
                comprobante.cae = item['CAE']
                comprobante.vto_cae = datetime.strptime(item['CAEFchVto'], '%Y%m%d').date()
                comprobante.afip_resultado = "A"
                comprobante.afip_observaciones = "Aprobado"
                comprobante.afip_error = None
                # FIX RECURSION
                comprobante.save(update_fields=['cae', 'vto_cae', 'afip_resultado', 'afip_error', 'afip_observaciones'])
                print("🎉 ¡CAE OBTENIDO!")
                return True
            else:
                msgs = []
                if 'Observaciones' in item:
                    obs = item['Observaciones']
                    if isinstance(obs, list):
                        for o in obs:
                            if 'Obs' in o: msgs.append(str(o['Obs']['Msg']))
                    elif isinstance(obs, dict) and 'Obs' in obs:
                        msgs.append(str(obs['Obs']['Msg']))

                err_final = " | ".join(msgs)
                comprobante.afip_error = f"Rechazado: {err_final}"
                # FIX RECURSION
                comprobante.save(update_fields=['afip_error'])
                raise Exception(f"Rechazo AFIP: {err_final}")

        except Exception as e:
            err_msg = str(e)
            print(f"❌ Error: {err_msg}")
            comprobante.afip_error = err_msg
            # FIX RECURSION
            comprobante.save(update_fields=['afip_error'])
            raise Exception(err_msg)