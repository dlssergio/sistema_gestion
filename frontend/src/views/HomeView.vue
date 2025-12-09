<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import axios from 'axios'
import { message } from 'ant-design-vue'
import { BankOutlined, RiseOutlined, WalletOutlined, AuditOutlined } from '@ant-design/icons-vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import { useConfigStore } from '@/stores/config'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
)

const configStore = useConfigStore()
const loading = ref(true)
const metrics = ref({ liquidez: 0, ventas_mes: 0, a_cobrar: 0, cheques_cartera: 0, a_pagar: 0 })

// Estado local para forzar actualización del gráfico
const chartKey = ref(0)

const chartDataConfig = ref({
  labels: [],
  datasets: [
    {
      label: 'Ventas ($)',
      backgroundColor: 'rgba(59, 130, 246, 0.1)',
      borderColor: '#3b82f6',
      borderWidth: 2,
      pointBackgroundColor: '#fff',
      pointBorderColor: '#3b82f6',
      pointRadius: 4,
      fill: true,
      tension: 0.4,
      data: [],
    },
  ],
})

// Opciones reactivas
const chartOptions = computed(() => {
  const isDark = configStore.currentTheme === 'dark'
  const textColor = isDark ? '#94a3b8' : '#64748b'
  const gridColor = isDark ? '#334155' : '#e2e8f0'

  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      y: {
        beginAtZero: true,
        grid: { borderDash: [2, 4], color: gridColor },
        ticks: {
          color: textColor,
          callback: (v) => `$${v.toLocaleString('es-AR', { notation: 'compact' })}`,
        },
      },
      x: {
        grid: { display: false },
        ticks: { color: textColor },
      },
    },
  }
})

// VIGILANTE: Si cambia el tema, forzamos redibujado del gráfico
watch(
  () => configStore.currentTheme,
  () => {
    chartKey.value++ // Cambia la key del componente para recrearlo
  },
)

const fetchMetrics = async () => {
  loading.value = true
  try {
    const response = await axios.get('http://tenant1.localhost:8000/api/dashboard/metrics/')
    metrics.value = response.data
    if (response.data.chart_labels) {
      chartDataConfig.value = {
        ...chartDataConfig.value,
        labels: JSON.parse(response.data.chart_labels),
        datasets: [
          {
            ...chartDataConfig.value.datasets[0],
            data: JSON.parse(response.data.chart_data),
          },
        ],
      }
    }
  } catch (e) {
    console.error(e)
    message.error('Error cargando métricas')
  } finally {
    loading.value = false
  }
}

const money = (val) =>
  `$ ${parseFloat(val || 0).toLocaleString('es-AR', { maximumFractionDigits: 0 })}`

onMounted(() => fetchMetrics())
</script>

<template>
  <div class="dashboard-container">
    <div class="mb-6">
      <h2 class="page-title">Resumen Ejecutivo</h2>
      <p class="page-subtitle">Visión general del estado del negocio.</p>
    </div>

    <a-row :gutter="[20, 20]" class="mb-6">
      <a-col
        :xs="24"
        :sm="12"
        :lg="6"
        v-for="(kpi, index) in [
          {
            title: 'Ventas del Mes',
            val: metrics.ventas_mes,
            icon: RiseOutlined,
            grad: 'blue-gradient',
            sub: '',
          },
          {
            title: 'Liquidez Total',
            val: metrics.liquidez,
            icon: BankOutlined,
            grad: 'green-gradient',
            sub: 'Caja + Bancos',
          },
          {
            title: 'Por Cobrar',
            val: metrics.a_cobrar,
            icon: WalletOutlined,
            grad: 'purple-gradient',
            sub: `Cheques: ${money(metrics.cheques_cartera)}`,
          },
          {
            title: 'Por Pagar',
            val: metrics.a_pagar,
            icon: AuditOutlined,
            grad: 'red-gradient',
            sub: 'Proveedores',
            isRed: true,
          },
        ]"
        :key="index"
      >
        <a-card :bordered="false" class="kpi-card" :loading="loading">
          <div class="kpi-content">
            <div class="kpi-icon" :class="kpi.grad">
              <component :is="kpi.icon" />
            </div>
            <div class="kpi-data">
              <div class="kpi-title">{{ kpi.title }}</div>
              <div class="kpi-value" :class="{ 'text-red': kpi.isRed }">{{ money(kpi.val) }}</div>
              <small class="kpi-sub" v-if="kpi.sub">{{ kpi.sub }}</small>
            </div>
          </div>
        </a-card>
      </a-col>
    </a-row>

    <a-card :bordered="false" title="Evolución de Ventas" class="chart-card" :loading="loading">
      <div class="chart-container">
        <Line
          :key="chartKey"
          v-if="chartDataConfig.labels.length > 0"
          :data="chartDataConfig"
          :options="chartOptions"
        />
        <div v-else class="no-data">Sin datos recientes.</div>
      </div>
    </a-card>
  </div>
</template>

<style scoped>
.dashboard-container {
  max-width: 1600px;
  margin: 0 auto;
}

/* Variables dinámicas para textos custom */
.page-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--ant-color-text);
  margin: 0;
}
.page-subtitle {
  color: var(--ant-color-text-secondary);
  margin-top: 5px;
}

/* Cards */
.kpi-card,
.chart-card {
  border-radius: 12px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
  transition: transform 0.2s;
  /* Ant Design maneja el background automáticamente gracias al ConfigProvider */
}
.kpi-card:hover {
  transform: translateY(-4px);
}

.kpi-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.kpi-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: white;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
}
.blue-gradient {
  background: linear-gradient(135deg, #3b82f6 0%, #1e40af 100%);
}
.green-gradient {
  background: linear-gradient(135deg, #10b981 0%, #047857 100%);
}
.purple-gradient {
  background: linear-gradient(135deg, #8b5cf6 0%, #5b21b6 100%);
}
.red-gradient {
  background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%);
}

.kpi-data {
  flex: 1;
}
.kpi-title {
  font-size: 0.85rem;
  color: var(--ant-color-text-secondary);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.kpi-value {
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--ant-color-text);
  margin-top: 4px;
}
.kpi-sub {
  color: var(--ant-color-text-secondary);
  display: block;
  margin-top: 4px;
}
.text-red {
  color: #ef4444;
}

.chart-container {
  height: 350px;
  position: relative;
}
.no-data {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ant-color-text-secondary);
}
.mb-6 {
  margin-bottom: 24px;
}
</style>
