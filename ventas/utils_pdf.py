# ventas/utils_pdf.py
import base64
import json
import qrcode
from io import BytesIO


def generar_qr_afip(comprobante):
    """
    Genera el QR en Base64 según especificación AFIP RG 4291.
    """
    try:
        # Recuperamos la empresa desde la configuración global o del comprobante
        # Asumimos que tienes acceso a la configuración de la empresa
        from parametros.models import ConfiguracionEmpresa
        config = ConfiguracionEmpresa.objects.first()
        cuit_emisor = int(config.entidad.cuit) if config else 0

        # Datos requeridos por AFIP
        datos_comprobante = {
            "ver": 1,
            "fecha": comprobante.fecha.strftime('%Y-%m-%d'),
            "cuit": cuit_emisor,
            "ptoVta": comprobante.punto_venta,
            "tipoCmp": int(comprobante.tipo_comprobante.codigo_afip),
            "nroCmp": comprobante.numero,
            "importe": float(comprobante.total),
            "moneda": "PES",
            "ctz": 1,
            "tipoDocRec": int(getattr(comprobante.cliente.entidad, 'cuit_tipo', 99)) if comprobante.cliente else 99,
            "nroDocRec": int(
                comprobante.cliente.entidad.cuit) if comprobante.cliente and comprobante.cliente.entidad.cuit else 0,
            "tipoCodAut": "E",  # 'E' para CAE
            "codAut": int(comprobante.cae) if comprobante.cae else 0
        }

        # 1. Convertir JSON a String
        json_str = json.dumps(datos_comprobante)

        # 2. Codificar JSON a Base64
        json_b64 = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')

        # 3. URL Final AFIP
        url_final = f"https://www.afip.gob.ar/fe/qr/?p={json_b64}"

        # 4. Generar Imagen QR
        qr = qrcode.make(url_final)
        buffered = BytesIO()
        qr.save(buffered, format="PNG")

        # 5. Retornar imagen en base64
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{img_str}"

    except Exception as e:
        print(f"Error generando QR: {e}")
        return None