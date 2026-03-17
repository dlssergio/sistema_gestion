<script setup>
import { computed, reactive, ref, watch, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import {
  DeleteOutlined,
  CreditCardOutlined,
  BankOutlined,
  WalletOutlined,
  SwapOutlined,
} from '@ant-design/icons-vue'
import api from '@/services/api'

const props = defineProps({
  open: { type: Boolean, default: false },
  total: { type: Number, default: 0 },
})

const emit = defineEmits(['update:open', 'confirm', 'cancel'])

const internalOpen = computed({
  get: () => props.open,
  set: (v) => emit('update:open', v),
})

const round2 = (n) => Math.round((Number(n) || 0) * 100) / 100
const money = (n) =>
  (Number(n) || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

// Amount field formatter/parser — AR format (dot = thousands, comma = decimal)
// Parser is intentionally simple: strip all dots (thousands), convert comma→dot (decimal).
// This avoids the Ant Design InputNumber bug where "$ 10.000" is misread as decimal 10.0
// during keystroke validation, silently capping input at 4 digits.
const fmtAmount = (v) => {
  if (v === '' || v == null) return ''
  const n = Number(String(v).replace(/\./g, '').replace(',', '.'))
  if (!Number.isFinite(n)) return String(v)
  // Format with AR locale (dot = thousands separator)
  return '$ ' + n.toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}
const parseAmount = (v) => {
  // Remove "$", spaces, then strip all dots (=thousands sep) and convert comma to decimal point
  const s = String(v || '')
    .replace(/\$\s?/g, '')
    .trim()
    .replace(/\./g, '')
    .replace(',', '.')
  const n = Number(s)
  return Number.isFinite(n) ? n : 0
}

// ── Catalogs ─────────────────────────────────────────────────────────────────
const loadingCatalogs = ref(false)
const tiposValor = ref([])
const cuentasFondo = ref([])
const bancos = ref([])
const planesCuota = ref([])

const DEFAULT_CAJA_EFECTIVO_ID = 1
const DEFAULT_CUENTA_TARJETAS_ID = 3
const DEFAULT_CUENTA_TRANSFERENCIA_ID = 2

const state = reactive({ pagos: [] })
const confirmedClose = ref(false)
const confirmLoading = ref(false)
let catalogsLoaded = false // guard: avoid re-fetching if already loaded in same session

// ── Theme primary color (mirrors POSView readPrimaryFromCss) ──────────────────
const pmPrimary = ref('#1677ff')
const readPrimary = () => {
  const read = (el, name) => (el ? getComputedStyle(el).getPropertyValue(name).trim() : '')
  const v =
    read(document.body, '--primary') ||
    read(document.body, '--sider-accent') ||
    read(document.body, '--primary-2') ||
    read(document.documentElement, '--primary') ||
    read(document.documentElement, '--sider-accent') ||
    read(document.documentElement, '--primary-2')
  if (v) pmPrimary.value = v
}
onMounted(() => readPrimary())
// ── Helpers ───────────────────────────────────────────────────────────────────
const getMetodoCodeFromTipoValor = (tipo) => {
  const nombre = String(tipo?.nombre || '').toLowerCase()
  if (nombre.includes('efect')) return 'EF'
  if (nombre.includes('débito') || nombre.includes('debito')) return 'DB'
  if (nombre.includes('crédito') || nombre.includes('credito')) return 'CR'
  if (nombre.includes('transf')) return 'TR'
  if (tipo?.es_cheque) return 'CH'
  return 'OT'
}

const getTipoValorById = (id) => tiposValor.value.find((t) => Number(t.id) === Number(id)) || null
const getPlanCuotaById = (id) => planesCuota.value.find((p) => Number(p.id) === Number(id)) || null

const isTarjetaTipo = (tipoId) => Boolean(getTipoValorById(tipoId)?.es_tarjeta)
const requiereBancoTipo = (tipoId) => Boolean(getTipoValorById(tipoId)?.requiere_banco)
const isChequeTipo = (tipoId) => Boolean(getTipoValorById(tipoId)?.es_cheque)

const cuentasOptions = computed(() =>
  cuentasFondo.value.map((c) => ({ value: c.id, label: c.nombre, tipo: c.tipo })),
)
const cuentasBancoOptions = computed(() =>
  cuentasFondo.value
    .filter((c) => String(c.tipo || '').toUpperCase() === 'BANCO')
    .map((c) => ({ value: c.id, label: c.nombre, tipo: c.tipo })),
)
const bancosOptions = computed(() => bancos.value.map((b) => ({ value: b.id, label: b.nombre })))
const tiposValorOptions = computed(() =>
  tiposValor.value.map((t) => ({ value: t.id, label: t.nombre, raw: t })),
)

const inferCardKind = (name) => {
  const s = String(name || '').toLowerCase()
  if (s.includes('debito') || s.includes('débito')) return 'DB'
  if (s.includes('credito') || s.includes('crédito')) return 'CR'
  return 'UNK'
}

const buildTarjetasForPago = (pago) => {
  const tipo = getTipoValorById(pago.tipo_valor)
  const metodo = getMetodoCodeFromTipoValor(tipo)
  if (metodo !== 'DB' && metodo !== 'CR') return []
  const unique = new Map()
  for (const p of planesCuota.value) {
    const tarjetaNombre = String(p?.tarjeta || '').trim()
    if (!tarjetaNombre) continue
    const kind = inferCardKind(tarjetaNombre)
    const allow =
      metodo === 'DB' ? kind === 'DB' || kind === 'UNK' : kind === 'CR' || kind === 'UNK'
    if (!allow) continue
    if (!unique.has(tarjetaNombre))
      unique.set(tarjetaNombre, { value: tarjetaNombre, label: tarjetaNombre })
  }
  return [...unique.values()].sort((a, b) => a.label.localeCompare(b.label))
}

const getTarjetaOptions = (pago) => buildTarjetasForPago(pago)

const getPlanesOptions = (pago) => {
  if (!pago.tarjeta_nombre) return []
  const tipo = getTipoValorById(pago.tipo_valor)
  const metodo = getMetodoCodeFromTipoValor(tipo)
  return planesCuota.value
    .filter((p) => String(p?.tarjeta || '').trim() === String(pago.tarjeta_nombre || '').trim())
    .filter((p) => {
      const kind = inferCardKind(p?.tarjeta || '')
      if (metodo === 'DB') return kind === 'DB' || kind === 'UNK'
      if (metodo === 'CR') return kind === 'CR' || kind === 'UNK'
      return false
    })
    .map((p) => ({
      value: p.id,
      label: `${p.plan_nombre} — ${p.cuotas} cuota${p.cuotas > 1 ? 's' : ''} (coef. ${p.coeficiente})`,
      raw: p,
    }))
    .sort((a, b) => a.label.localeCompare(b.label))
}

const buildEmptyPago = (tipoValorId = null) => ({
  key: `${Date.now()}-${Math.random()}`,
  tipo_valor: tipoValorId,
  destino: null,
  monto: 0,
  referencia: '',
  banco_origen: null,
  fecha_cobro: null,
  cuit_librador: '',
  opcion_cuota: null,
  tarjeta_nombre: null,
  tarjeta_lote: '',
  tarjeta_cupon: '',
  efectivo_recibido: null,
})

const isDestinoLocked = (pago) => {
  const metodo = getMetodoCodeFromTipoValor(getTipoValorById(pago.tipo_valor))
  return metodo === 'EF' || metodo === 'DB' || metodo === 'CR'
}
const getDestinoOptions = (pago) => {
  const metodo = getMetodoCodeFromTipoValor(getTipoValorById(pago.tipo_valor))
  return metodo === 'TR' || metodo === 'CH' ? cuentasBancoOptions.value : cuentasOptions.value
}

const ensureDestinoValido = (pago) => {
  const metodo = getMetodoCodeFromTipoValor(getTipoValorById(pago.tipo_valor))
  if (metodo === 'TR' || metodo === 'CH') {
    const existe = cuentasBancoOptions.value.some((c) => Number(c.value) === Number(pago.destino))
    if (!existe) pago.destino = metodo === 'TR' ? DEFAULT_CUENTA_TRANSFERENCIA_ID : null
    return
  }
  const existe = cuentasOptions.value.some((c) => Number(c.value) === Number(pago.destino))
  if (!existe) pago.destino = null
}

const setDefaultsForPago = (pago) => {
  const metodo = getMetodoCodeFromTipoValor(getTipoValorById(pago.tipo_valor))
  if (metodo === 'EF') {
    pago.destino = DEFAULT_CAJA_EFECTIVO_ID
    if (!pago.efectivo_recibido || Number(pago.efectivo_recibido) <= 0)
      pago.efectivo_recibido = round2(pago.monto || 0)
  } else if (metodo === 'DB' || metodo === 'CR') {
    pago.destino = DEFAULT_CUENTA_TARJETAS_ID
    pago.efectivo_recibido = null
  } else if (metodo === 'TR') {
    pago.destino = DEFAULT_CUENTA_TRANSFERENCIA_ID
    pago.efectivo_recibido = null
  } else if (metodo === 'CH') {
    pago.efectivo_recibido = null
    ensureDestinoValido(pago)
  } else {
    pago.efectivo_recibido = null
  }
  ensureDestinoValido(pago)
}

const inferDefaultTipoValorId = (methodCode) => {
  const find = (substr) =>
    tiposValor.value.find((t) =>
      String(t.nombre || '')
        .toLowerCase()
        .includes(substr),
    )?.id || null
  if (methodCode === 'EF') return find('efect')
  if (methodCode === 'DB') return find('débito') || find('debito')
  if (methodCode === 'CR') return find('crédito') || find('credito')
  if (methodCode === 'TR') return find('transf')
  return null
}

// ── Computed totals ───────────────────────────────────────────────────────────
const getCoeficientePago = (pago) => {
  if (!isTarjetaTipo(pago.tipo_valor)) return 1
  const plan = getPlanCuotaById(pago.opcion_cuota)
  const coef = Number(plan?.coeficiente ?? 1)
  return Number.isFinite(coef) && coef > 0 ? coef : 1
}
const getRecargoPago = (pago) => {
  if (!isTarjetaTipo(pago.tipo_valor)) return 0
  const base = round2(pago.monto || 0)
  const coef = getCoeficientePago(pago)
  return coef <= 1 ? 0 : round2(base * coef - base)
}
const getDescuentoPago = (pago) => {
  if (!isTarjetaTipo(pago.tipo_valor)) return 0
  const base = round2(pago.monto || 0)
  const coef = getCoeficientePago(pago)
  return coef >= 1 ? 0 : round2(base - base * coef)
}
const getCobroFinalPago = (pago) =>
  round2(round2(pago.monto || 0) + getRecargoPago(pago) - getDescuentoPago(pago))

const addPago = (methodCode = 'EF') => {
  const tipoId = inferDefaultTipoValorId(methodCode)
  const pago = buildEmptyPago(tipoId)
  setDefaultsForPago(pago)
  const pendiente = saldoPendienteBase.value
  pago.monto = pendiente > 0 ? pendiente : 0
  if (methodCode === 'EF') pago.efectivo_recibido = pago.monto
  state.pagos.push(pago)
}

const removePago = (index) => state.pagos.splice(index, 1)

const totalBasePagos = computed(() => round2(state.pagos.reduce((a, p) => a + round2(p.monto), 0)))
const totalRecargos = computed(() => round2(state.pagos.reduce((a, p) => a + getRecargoPago(p), 0)))
const totalDescuentos = computed(() =>
  round2(state.pagos.reduce((a, p) => a + getDescuentoPago(p), 0)),
)
const totalFinalCobro = computed(() =>
  round2(round2(props.total) + totalRecargos.value - totalDescuentos.value),
)
const totalCobradoLineas = computed(() =>
  round2(state.pagos.reduce((a, p) => a + getCobroFinalPago(p), 0)),
)
const saldoPendienteBase = computed(() => round2(props.total - totalBasePagos.value))

const totalEfectivoRecibido = computed(() =>
  round2(
    state.pagos.reduce((a, p) => {
      const m = getMetodoCodeFromTipoValor(getTipoValorById(p.tipo_valor))
      return m !== 'EF' ? a : a + round2(p.efectivo_recibido ?? 0)
    }, 0),
  ),
)
const totalEfectivoAplicado = computed(() =>
  round2(
    state.pagos.reduce((a, p) => {
      const m = getMetodoCodeFromTipoValor(getTipoValorById(p.tipo_valor))
      return m !== 'EF' ? a : a + round2(p.monto ?? 0)
    }, 0),
  ),
)
const vueltoTotal = computed(() => {
  const diff = round2(totalEfectivoRecibido.value - totalEfectivoAplicado.value)
  return diff > 0 ? diff : 0
})

// ── Catalog loading ───────────────────────────────────────────────────────────
const loadCatalogs = async () => {
  if (loadingCatalogs.value) return // guard against concurrent calls
  loadingCatalogs.value = true
  try {
    const [tiposRes, cuentasRes, bancosRes, planesRes] = await Promise.all([
      api.get('/api/tipos-valores/'),
      api.get('/api/cuentas-fondo/', { params: { activa: true } }),
      api.get('/api/bancos/'),
      api.get('/api/planes-cuota/'),
    ])
    tiposValor.value = Array.isArray(tiposRes.data) ? tiposRes.data : tiposRes.data?.results || []
    cuentasFondo.value = Array.isArray(cuentasRes.data)
      ? cuentasRes.data
      : cuentasRes.data?.results || []
    bancos.value = Array.isArray(bancosRes.data) ? bancosRes.data : bancosRes.data?.results || []
    planesCuota.value = Array.isArray(planesRes.data)
      ? planesRes.data
      : planesRes.data?.results || []
  } catch (error) {
    console.error(error)
    message.error('No se pudieron cargar los catálogos de medios de pago.')
  } finally {
    loadingCatalogs.value = false
  }
}

const resetState = async () => {
  catalogsLoaded = false // always reload when modal opens
  await loadCatalogs()
  catalogsLoaded = true
  state.pagos = []
  addPago('EF')
}

watch(
  () => props.open,
  async (v) => {
    if (!v) return
    // Read theme color immediately and after next frame (CSS vars may not be ready yet)
    readPrimary()
    requestAnimationFrame(readPrimary)
    confirmedClose.value = false
    await resetState()
  },
)

// ── Event handlers ────────────────────────────────────────────────────────────
const onTipoValorChange = (pago) => {
  pago.banco_origen = null
  pago.opcion_cuota = null
  pago.tarjeta_nombre = null
  pago.tarjeta_lote = ''
  pago.tarjeta_cupon = ''
  pago.cuit_librador = ''
  pago.fecha_cobro = null
  pago.referencia = ''
  setDefaultsForPago(pago)
}
const onTarjetaChange = (pago) => {
  pago.opcion_cuota = null
}

/** Max allowed monto for a given pago line:
 *  = what this line currently has + what's still unpaid by OTHER lines
 *  This prevents a single line from exceeding the total comprobante. */
const getMaxMonto = (pago) => {
  const otherLines = state.pagos
    .filter((p) => p.key !== pago.key)
    .reduce((a, p) => a + round2(p.monto || 0), 0)
  return Math.max(0, round2(round2(props.total) - otherLines))
}

/** Auto-sync efectivo_recibido for EF lines when the base amount changes */
const onMontoChange = (pago) => {
  const metodo = getMetodoCodeFromTipoValor(getTipoValorById(pago.tipo_valor))
  if (metodo !== 'EF') return
  // Only auto-sync if vuelto was 0 (user hadn't manually entered a different received amount)
  const currentVuelto = round2((pago.efectivo_recibido ?? 0) - (pago.monto ?? 0))
  if (currentVuelto <= 0) pago.efectivo_recibido = round2(pago.monto || 0)
}

const validarPago = (pago, idx) => {
  const n = idx + 1
  if (!pago.tipo_valor) {
    message.warning(`Seleccioná el tipo de valor en la línea ${n}.`)
    return false
  }
  if (!pago.destino) {
    message.warning(`Seleccioná la cuenta/caja destino en la línea ${n}.`)
    return false
  }
  if (round2(pago.monto) <= 0) {
    message.warning(`El monto debe ser mayor a 0 en la línea ${n}.`)
    return false
  }
  if (requiereBancoTipo(pago.tipo_valor) && !pago.banco_origen) {
    message.warning(`Seleccioná banco de origen en la línea ${n}.`)
    return false
  }

  const metodo = getMetodoCodeFromTipoValor(getTipoValorById(pago.tipo_valor))
  if ((metodo === 'DB' || metodo === 'CR') && !pago.tarjeta_nombre) {
    message.warning(`Seleccioná la tarjeta en la línea ${n}.`)
    return false
  }
  if ((metodo === 'DB' || metodo === 'CR') && !pago.opcion_cuota) {
    message.warning(`Seleccioná el plan / cuotas en la línea ${n}.`)
    return false
  }
  if ((metodo === 'TR' || metodo === 'CH') && !pago.destino) {
    message.warning(`Seleccioná la cuenta bancaria destino en la línea ${n}.`)
    return false
  }
  if (metodo === 'EF' && round2(pago.efectivo_recibido ?? 0) < round2(pago.monto)) {
    message.warning(`El efectivo recibido no alcanza en la línea ${n}.`)
    return false
  }
  return true
}

const buildPayloadPago = (pago) => {
  const tipo = getTipoValorById(pago.tipo_valor)
  const metodo = getMetodoCodeFromTipoValor(tipo)
  const monto = round2(pago.monto)
  const payload = {
    metodo,
    tipo_valor: pago.tipo_valor,
    destino: pago.destino,
    monto,
    referencia: pago.referencia || '',
    nota: pago.referencia || '',
    banco_origen: pago.banco_origen || null,
    fecha_cobro: pago.fecha_cobro || null,
    cuit_librador: pago.cuit_librador || '',
    opcion_cuota: pago.opcion_cuota || null,
    tarjeta_nombre: pago.tarjeta_nombre || '',
    tarjeta_lote: pago.tarjeta_lote || '',
    tarjeta_cupon: pago.tarjeta_cupon || '',
    recargo_preview: getRecargoPago(pago),
    descuento_preview: getDescuentoPago(pago),
    total_cobro_preview: getCobroFinalPago(pago),
  }
  if (metodo === 'EF') {
    const ef = round2(pago.efectivo_recibido ?? monto)
    payload.efectivo_recibido = ef
    payload.vuelto = round2(Math.max(0, ef - monto))
  } else {
    payload.efectivo_recibido = undefined
    payload.vuelto = 0
  }
  return payload
}

const handleCancel = () => {
  internalOpen.value = false
  if (!confirmedClose.value) emit('cancel')
}

const confirm = () => {
  if (confirmLoading.value) return
  if (!state.pagos.length) {
    message.warning('Debés cargar al menos una forma de pago.')
    return
  }
  for (let i = 0; i < state.pagos.length; i++) if (!validarPago(state.pagos[i], i)) return
  if (totalBasePagos.value < round2(props.total)) {
    message.warning(`Falta cubrir $ ${money(saldoPendienteBase.value)} del total base.`)
    return
  }
  // Warn but don't block on overpayment (cash rounding is valid)
  if (saldoPendienteBase.value < -0.01) {
    message.warning(
      `Atención: el total cargado supera el comprobante en $ ${money(Math.abs(saldoPendienteBase.value))}.`,
    )
  }
  confirmLoading.value = true
  confirmedClose.value = true
  emit('confirm', {
    pagos: state.pagos.map(buildPayloadPago),
    total_base: round2(props.total),
    total_apagar: totalFinalCobro.value,
    recargos_total: totalRecargos.value,
    descuentos_total: totalDescuentos.value,
    vuelto: vueltoTotal.value,
  })
  internalOpen.value = false
  confirmLoading.value = false
}

// ── UI helpers ────────────────────────────────────────────────────────────────
const metodoBadge = (pago) => {
  const m = getMetodoCodeFromTipoValor(getTipoValorById(pago.tipo_valor))
  const MAP = {
    EF: { label: 'Efectivo', cls: 'badge--ef' },
    DB: { label: 'Débito', cls: 'badge--db' },
    CR: { label: 'Crédito', cls: 'badge--cr' },
    TR: { label: 'Transferencia', cls: 'badge--tr' },
    CH: { label: 'Cheque', cls: 'badge--ch' },
    OT: { label: 'Otro', cls: 'badge--ot' },
  }
  return MAP[m] || MAP['OT']
}
</script>

<template>
  <a-modal
    v-model:open="internalOpen"
    title="Cobro"
    width="1060px"
    centered
    :maskClosable="false"
    :footer="null"
    class="pm-modal"
    @cancel="handleCancel"
  >
    <div class="pm-root" :style="{ '--pm-primary': pmPrimary }">
      <!-- ── Quick-add toolbar ──────────────────────────────────────────── -->
      <div class="pm-toolbar">
        <span class="toolbar-label">Agregar forma de pago</span>
        <div class="toolbar-btns">
          <button class="tbtn tbtn--ef" @click="addPago('EF')" type="button">
            <WalletOutlined /> Efectivo
          </button>
          <button class="tbtn tbtn--db" @click="addPago('DB')" type="button">
            <CreditCardOutlined /> Débito
          </button>
          <button class="tbtn tbtn--cr" @click="addPago('CR')" type="button">
            <CreditCardOutlined /> Crédito
          </button>
          <button class="tbtn tbtn--tr" @click="addPago('TR')" type="button">
            <SwapOutlined /> Transferencia
          </button>
        </div>
      </div>

      <!-- ── Main body ──────────────────────────────────────────────────── -->
      <div class="pm-body">
        <!-- Left: payment lines -->
        <div class="pm-form">
          <div class="pm-section-title">Formas de pago</div>

          <div v-if="loadingCatalogs" class="pm-loading">
            <span class="loading-dot" /><span class="loading-dot" /><span class="loading-dot" />
            Cargando catálogos...
          </div>

          <div v-else class="pm-lines">
            <div class="pm-line" v-for="(pago, index) in state.pagos" :key="pago.key">
              <!-- Line header -->
              <div class="pm-line-header">
                <div class="pm-line-header-left">
                  <span class="line-num">{{ index + 1 }}</span>
                  <span class="badge" :class="metodoBadge(pago).cls">
                    {{ metodoBadge(pago).label }}
                  </span>
                </div>
                <button
                  class="remove-btn"
                  :disabled="state.pagos.length === 1"
                  @click="removePago(index)"
                  type="button"
                  title="Eliminar línea"
                >
                  <DeleteOutlined />
                </button>
              </div>

              <!-- Fields grid -->
              <div class="pm-grid">
                <div class="pm-field">
                  <label>Tipo de valor</label>
                  <a-select
                    v-model:value="pago.tipo_valor"
                    :options="tiposValorOptions"
                    size="large"
                    style="width: 100%"
                    @change="() => onTipoValorChange(pago)"
                  />
                </div>

                <div class="pm-field">
                  <label>Cuenta / Caja destino</label>
                  <a-select
                    v-model:value="pago.destino"
                    :options="getDestinoOptions(pago)"
                    size="large"
                    style="width: 100%"
                    :disabled="isDestinoLocked(pago)"
                    placeholder="Seleccionar cuenta"
                  />
                </div>

                <div class="pm-field">
                  <label>Monto base</label>
                  <a-input-number
                    v-model:value="pago.monto"
                    style="width: 100%"
                    :min="0"
                    :max="getMaxMonto(pago)"
                    :step="100"
                    :formatter="fmtAmount"
                    :parser="parseAmount"
                    size="large"
                    class="amount-input"
                    @change="() => onMontoChange(pago)"
                  />
                </div>

                <div
                  class="pm-field"
                  v-if="getMetodoCodeFromTipoValor(getTipoValorById(pago.tipo_valor)) === 'EF'"
                >
                  <label>Efectivo recibido</label>
                  <a-input-number
                    v-model:value="pago.efectivo_recibido"
                    style="width: 100%"
                    :min="0"
                    :step="100"
                    :formatter="fmtAmount"
                    :parser="parseAmount"
                    size="large"
                    class="amount-input"
                  />
                </div>

                <div class="pm-field" v-if="requiereBancoTipo(pago.tipo_valor)">
                  <label>Banco origen</label>
                  <a-select
                    v-model:value="pago.banco_origen"
                    :options="bancosOptions"
                    size="large"
                    style="width: 100%"
                  />
                </div>

                <template v-if="isTarjetaTipo(pago.tipo_valor)">
                  <div class="pm-field">
                    <label>Tarjeta</label>
                    <a-select
                      v-model:value="pago.tarjeta_nombre"
                      :options="getTarjetaOptions(pago)"
                      size="large"
                      style="width: 100%"
                      allowClear
                      placeholder="Seleccionar tarjeta"
                      @change="() => onTarjetaChange(pago)"
                    />
                  </div>
                  <div class="pm-field">
                    <label>Plan / Cuotas</label>
                    <a-select
                      v-model:value="pago.opcion_cuota"
                      :options="getPlanesOptions(pago)"
                      size="large"
                      style="width: 100%"
                      allowClear
                      :disabled="!pago.tarjeta_nombre"
                      placeholder="Seleccionar plan"
                    />
                  </div>
                  <div class="pm-field">
                    <label>Lote</label>
                    <a-input v-model:value="pago.tarjeta_lote" size="large" />
                  </div>
                  <div class="pm-field">
                    <label>Cupón</label>
                    <a-input v-model:value="pago.tarjeta_cupon" size="large" />
                  </div>
                </template>

                <div class="pm-field" v-if="isChequeTipo(pago.tipo_valor)">
                  <label>CUIT librador</label>
                  <a-input v-model:value="pago.cuit_librador" size="large" />
                </div>

                <div class="pm-field pm-field--wide">
                  <label>Referencia / Nota</label>
                  <a-input
                    v-model:value="pago.referencia"
                    placeholder="Ej: operación, ticket, observación"
                    size="large"
                  />
                </div>
              </div>

              <!-- Line subtotal -->
              <div class="pm-line-footer">
                <div class="line-footer-item" v-if="getRecargoPago(pago) > 0">
                  <span>Recargo</span>
                  <span class="lf-val lf-val--surcharge"
                    >+ $ {{ money(getRecargoPago(pago)) }}</span
                  >
                </div>
                <div class="line-footer-item" v-if="getDescuentoPago(pago) > 0">
                  <span>Descuento</span>
                  <span class="lf-val lf-val--discount"
                    >− $ {{ money(getDescuentoPago(pago)) }}</span
                  >
                </div>
                <div class="line-footer-total">
                  <span class="lf-label">Cobro de esta línea</span>
                  <span class="lf-amount">$ {{ money(getCobroFinalPago(pago)) }}</span>
                </div>
              </div>
            </div>
            <!-- /.pm-line -->
          </div>
          <!-- /.pm-lines -->
        </div>
        <!-- /.pm-form -->

        <!-- Right: summary panel -->
        <aside class="pm-summary">
          <div class="pm-section-title">Resumen</div>

          <div class="srow">
            <span>Total comprobante</span>
            <strong>$ {{ money(total) }}</strong>
          </div>
          <div class="srow">
            <span>Total base cargado</span>
            <strong>$ {{ money(totalBasePagos) }}</strong>
          </div>
          <div class="srow srow--warn" v-if="saldoPendienteBase > 0">
            <span>Saldo pendiente</span>
            <strong>$ {{ money(saldoPendienteBase) }}</strong>
          </div>
          <div class="srow srow--overpay" v-if="saldoPendienteBase < -0.01">
            <span>Excedente</span>
            <strong>+ $ {{ money(Math.abs(saldoPendienteBase)) }}</strong>
          </div>
          <div class="srow srow--surcharge" v-if="totalRecargos > 0">
            <span>Recargos</span>
            <strong>+ $ {{ money(totalRecargos) }}</strong>
          </div>
          <div class="srow srow--discount" v-if="totalDescuentos > 0">
            <span>Descuentos</span>
            <strong>− $ {{ money(totalDescuentos) }}</strong>
          </div>

          <div class="s-divider" />

          <div class="srow">
            <span>Cobrado por líneas</span>
            <strong>$ {{ money(totalCobradoLineas) }}</strong>
          </div>

          <div class="srow-total">
            <span class="st-label">Total a cobrar</span>
            <span class="st-amount">$ {{ money(totalFinalCobro) }}</span>
          </div>

          <div class="srow srow--vuelto" v-if="vueltoTotal > 0">
            <span>Vuelto efectivo</span>
            <strong>$ {{ money(vueltoTotal) }}</strong>
          </div>

          <button
            class="confirm-btn"
            :class="{
              'confirm-btn--disabled': saldoPendienteBase > 0,
              'confirm-btn--loading': confirmLoading,
            }"
            @click="confirm"
            type="button"
          >
            <span v-if="confirmLoading" class="confirm-spinner" />
            {{
              saldoPendienteBase > 0 ? `Faltan $ ${money(saldoPendienteBase)}` : 'Confirmar cobro'
            }}
          </button>

          <p class="pm-hint">Podés combinar múltiples formas de pago en una misma venta.</p>
        </aside>
      </div>
      <!-- /.pm-body -->
    </div>
    <!-- /.pm-root -->
  </a-modal>
</template>

<style scoped>
/* ── CSS variables (mirror POSView) ─────────────────────────────────────────── */
.pm-root {
  --accent-rgb: 99, 102, 241;
  --radius: 7px;
}

/* ── Root container ─────────────────────────────────────────────────────────── */
.pm-root {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 0 2px;
}

/* ── Toolbar ─────────────────────────────────────────────────────────────────── */
.pm-toolbar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  background: rgba(148, 163, 184, 0.04);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.toolbar-label {
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--text-2);
  white-space: nowrap;
}
.toolbar-btns {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.tbtn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: var(--radius);
  border: 1px solid transparent;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition:
    filter 0.12s ease,
    transform 0.1s ease;
  font-family: inherit;
}
.tbtn:hover {
  filter: brightness(1.08);
  transform: translateY(-1px);
}
.tbtn:active {
  transform: scale(0.97);
}

.tbtn--ef {
  background: rgba(16, 185, 129, 0.12);
  border-color: rgba(16, 185, 129, 0.3);
  color: #059669;
}
.tbtn--db {
  background: rgba(59, 130, 246, 0.12);
  border-color: rgba(59, 130, 246, 0.3);
  color: #2563eb;
}
.tbtn--cr {
  background: rgba(139, 92, 246, 0.12);
  border-color: rgba(139, 92, 246, 0.3);
  color: #7c3aed;
}
.tbtn--tr {
  background: rgba(245, 158, 11, 0.12);
  border-color: rgba(245, 158, 11, 0.3);
  color: #d97706;
}

/* ── Body layout ─────────────────────────────────────────────────────────────── */
.pm-body {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 14px;
  align-items: start;
}

/* ── Section title (shared) ──────────────────────────────────────────────────── */
.pm-section-title {
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-2);
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}

/* ── Form panel ──────────────────────────────────────────────────────────────── */
.pm-form {
  border: 1px solid var(--border);
  border-top: 2px solid var(--pm-primary, rgba(var(--accent-rgb), 1));
  background: var(--surface-1);
  border-radius: var(--radius);
  padding: 16px;
  max-height: 60vh;
  overflow-y: auto;
}

.pm-loading {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 20px 0;
  color: var(--text-2);
  font-size: 13px;
}
.loading-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--pm-primary, rgba(var(--accent-rgb), 0.6));
  animation: blink 1.2s ease-in-out infinite;
}
.loading-dot:nth-child(2) {
  animation-delay: 0.2s;
}
.loading-dot:nth-child(3) {
  animation-delay: 0.4s;
}
@keyframes blink {
  0%,
  80%,
  100% {
    opacity: 0.2;
  }
  40% {
    opacity: 1;
  }
}

/* ── Payment lines ───────────────────────────────────────────────────────────── */
.pm-lines {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pm-line {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: rgba(148, 163, 184, 0.03);
  overflow: hidden;
}

.pm-line-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: rgba(148, 163, 184, 0.05);
  border-bottom: 1px solid var(--border);
}
.pm-line-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.line-num {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.12);
  border: 1px solid rgba(99, 102, 241, 0.22);
  font-size: 11px;
  font-weight: 900;
  color: var(--pm-primary, rgba(var(--accent-rgb), 1));
}

/* Method badge */
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 9px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.04em;
  border: 1px solid transparent;
}
.badge--ef {
  background: rgba(16, 185, 129, 0.1);
  border-color: rgba(16, 185, 129, 0.25);
  color: #059669;
}
.badge--db {
  background: rgba(59, 130, 246, 0.1);
  border-color: rgba(59, 130, 246, 0.25);
  color: #2563eb;
}
.badge--cr {
  background: rgba(139, 92, 246, 0.1);
  border-color: rgba(139, 92, 246, 0.25);
  color: #7c3aed;
}
.badge--tr {
  background: rgba(245, 158, 11, 0.1);
  border-color: rgba(245, 158, 11, 0.25);
  color: #d97706;
}
.badge--ch {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.25);
  color: #dc2626;
}
.badge--ot {
  background: rgba(148, 163, 184, 0.1);
  border-color: rgba(148, 163, 184, 0.2);
  color: var(--text-2);
}

.remove-btn {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 5px;
  border: 1px solid rgba(239, 68, 68, 0.18);
  background: rgba(239, 68, 68, 0.05);
  color: #dc2626;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.12s;
  opacity: 0.7;
}
.remove-btn:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.12);
  opacity: 1;
}
.remove-btn:disabled {
  opacity: 0.25;
  cursor: not-allowed;
}

/* Fields grid */
.pm-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  padding: 14px;
}
.pm-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.pm-field--wide {
  grid-column: span 2;
}
.pm-field label {
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--text-2);
}

/* Amount input accent */
:global(.pm-root .amount-input .ant-input-number-input) {
  font-weight: 800 !important;
  font-variant-numeric: tabular-nums;
}

/* Line footer */
.pm-line-footer {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 20px;
  padding: 10px 14px;
  background: rgba(148, 163, 184, 0.04);
  border-top: 1px dashed var(--border);
}
.line-footer-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-2);
}
.lf-val {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.lf-val--surcharge {
  color: #f59e0b;
}
.lf-val--discount {
  color: #10b981;
}
.line-footer-total {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}
.lf-label {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-2);
}
.lf-amount {
  font-size: 15px;
  font-weight: 900;
  font-variant-numeric: tabular-nums;
  color: var(--text-0);
}

/* ── Summary panel ───────────────────────────────────────────────────────────── */
.pm-summary {
  border: 1px solid var(--border);
  border-top: 2px solid var(--pm-primary, rgba(var(--accent-rgb), 1));
  background: var(--surface-1);
  border-radius: var(--radius);
  padding: 16px;
  position: sticky;
  top: 0;
}

.srow {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  font-size: 13px;
  color: var(--text-1);
  font-variant-numeric: tabular-nums;
}
.srow strong {
  font-weight: 700;
  color: var(--text-0);
}
.srow--warn strong {
  color: #ef4444;
}
.srow--surcharge strong {
  color: #f59e0b;
}
.srow--discount strong {
  color: #10b981;
}
.srow--vuelto strong {
  color: #10b981;
  font-size: 14px;
}

.s-divider {
  height: 1px;
  background: var(--border);
  margin: 10px 0;
}

.srow-total {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 12px 14px;
  background: rgba(var(--accent-rgb), 0.06);
  border: 1px solid rgba(var(--accent-rgb), 0.18);
  border-radius: var(--radius);
  margin: 8px 0 4px;
}
.st-label {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-2);
}
.st-amount {
  font-size: 2rem;
  font-weight: 900;
  letter-spacing: -0.5px;
  font-variant-numeric: tabular-nums;
  color: var(--pm-primary, rgba(var(--accent-rgb), 1));
  line-height: 1.15;
}

/* Confirm button */
.confirm-btn {
  width: 100%;
  margin-top: 12px;
  height: 50px;
  border-radius: var(--radius);
  border: none;
  background: var(--pm-primary, rgba(var(--accent-rgb), 1));
  color: #fff;
  font-size: 14px;
  font-weight: 900;
  letter-spacing: 0.02em;
  cursor: pointer;
  transition:
    filter 0.14s ease,
    transform 0.1s ease,
    background 0.2s ease;
  font-family: inherit;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.confirm-btn:hover:not(.confirm-btn--disabled):not(.confirm-btn--loading) {
  filter: brightness(1.1);
  transform: translateY(-1px);
}
.confirm-btn:active:not(.confirm-btn--disabled) {
  transform: scale(0.98);
}
.confirm-btn--disabled {
  background: rgba(148, 163, 184, 0.25) !important;
  color: var(--text-2) !important;
  cursor: not-allowed;
}
.confirm-btn--loading {
  cursor: wait;
  opacity: 0.8;
}

/* Spinner for confirm loading */
.confirm-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  flex-shrink: 0;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Overpayment row */
.srow--overpay strong {
  color: #8b5cf6;
}

.pm-hint {
  margin-top: 10px;
  font-size: 11.5px;
  color: var(--text-2);
  line-height: 1.5;
  text-align: center;
}

/* ── Responsive ──────────────────────────────────────────────────────────────── */
@media (max-width: 900px) {
  .pm-body {
    grid-template-columns: 1fr;
  }
  .pm-summary {
    position: static;
  }
}
@media (max-width: 600px) {
  .pm-grid {
    grid-template-columns: 1fr;
  }
  .pm-field--wide {
    grid-column: span 1;
  }
}
</style>
