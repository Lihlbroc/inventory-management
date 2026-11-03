<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'

const { t, currentCurrency, translateProductName } = useI18n()

const STEP = 500
const DEBOUNCE_MS = 250

const loading = ref(true) // first load only (fetches full_cost for the slider max)
const error = ref(null)
const sliderMax = ref(STEP)
const budget = ref(0)
const recommendations = ref(null) // full API response, null until first success
const refreshing = ref(false) // a slider-driven fetch is pending or in flight
const submitting = ref(false)
const orderError = ref(null)
const placedOrder = ref(null)

let debounceTimer = null
// Monotonic id so a slow, older response can never overwrite a newer one.
let requestSeq = 0

const items = computed(() => recommendations.value?.items ?? [])

const money = (amount) => formatCurrency(amount, currentCurrency.value)
// Unit costs can be fractional, so keep cents for USD in per-unit and line figures.
const moneyExact = (amount) => formatCurrencyWithDecimals(amount, currentCurrency.value, 2)

const canPlaceOrder = computed(
  () => items.value.length > 0 && !submitting.value && !refreshing.value
)

const fetchRecommendations = async () => {
  const seq = ++requestSeq
  try {
    const data = await api.getRestockingRecommendations(budget.value)
    if (seq !== requestSeq) return // stale response, a newer request owns the state
    recommendations.value = data
    error.value = null
  } catch (err) {
    if (seq !== requestSeq) return
    error.value = t('restocking.loadError')
    console.error('Restocking load error:', err)
  } finally {
    if (seq === requestSeq) refreshing.value = false
  }
}

const onBudgetInput = () => {
  // Mark as refreshing immediately so "Place Order" can't submit stale lines during the debounce window.
  refreshing.value = true
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(fetchRecommendations, DEBOUNCE_MS)
}

const init = async () => {
  loading.value = true
  error.value = null
  try {
    // budget=0 still returns full_cost, which is the cost to cover every shortfall.
    const base = await api.getRestockingRecommendations(0)
    // Round up to a multiple of STEP so the slider's right end can always reach full coverage.
    sliderMax.value = Math.max(STEP, Math.ceil((base.full_cost || 0) / STEP) * STEP)
    budget.value = sliderMax.value
    await fetchRecommendations()
  } catch (err) {
    error.value = t('restocking.loadError')
    console.error('Restocking init error:', err)
  } finally {
    loading.value = false
  }
}

const placeOrder = async () => {
  if (!canPlaceOrder.value) return
  submitting.value = true
  orderError.value = null
  placedOrder.value = null
  try {
    const order = await api.createRestockingOrder({
      items: items.value.map(i => ({ sku: i.sku, quantity: i.quantity }))
    })
    placedOrder.value = order
    // Stock/shortfalls changed server-side, so reload the recommendations.
    await fetchRecommendations()
  } catch (err) {
    // Backend validation errors are 400 with { detail }.
    const detail = err.response?.data?.detail
    orderError.value = typeof detail === 'string' ? detail : t('restocking.orderError')
    console.error('Restocking order error:', err)
  } finally {
    submitting.value = false
  }
}

onMounted(init)
onBeforeUnmount(() => {
  clearTimeout(debounceTimer)
  requestSeq++ // invalidate any in-flight request
})
</script>

<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error && !recommendations" class="error">{{ error }}</div>
    <div v-else>
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budget') }}</h3>
          <span class="budget-readout">{{ money(budget) }}</span>
        </div>
        <input
          v-model.number="budget"
          class="budget-slider"
          type="range"
          min="0"
          :max="sliderMax"
          :step="STEP"
          :aria-label="t('restocking.budget')"
          @input="onBudgetInput"
        />
        <div class="slider-scale">
          <span>{{ money(0) }}</span>
          <span>{{ t('restocking.budgetMax', { amount: money(sliderMax) }) }}</span>
        </div>
        <p class="note">{{ t('restocking.stockNote') }}</p>
      </div>

      <div v-if="error" class="error">{{ error }}</div>

      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.totalCost') }}</div>
          <div class="stat-value">{{ money(recommendations?.total_cost ?? 0) }}</div>
        </div>
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.remainingBudget') }}</div>
          <div class="stat-value">{{ money(recommendations?.remaining_budget ?? 0) }}</div>
        </div>
      </div>

      <div v-if="placedOrder" class="success-banner" role="status">
        {{ t('restocking.orderSuccess', { orderNumber: placedOrder.order_number }) }}
        <router-link to="/orders">{{ t('restocking.viewOrders') }}</router-link>
      </div>
      <div v-if="orderError" class="error">{{ orderError }}</div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendations') }} ({{ items.length }})</h3>
          <button class="place-order" :disabled="!canPlaceOrder" @click="placeOrder">
            {{ submitting ? t('restocking.submitting') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="items.length === 0" class="empty">{{ t('restocking.empty') }}</div>
        <div v-else :class="['table-container', { dimmed: refreshing }]">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.name') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th class="num">{{ t('restocking.table.quantity') }}</th>
                <th class="num">{{ t('restocking.table.unitCost') }}</th>
                <th class="num">{{ t('restocking.table.lineCost') }}</th>
                <th>{{ t('restocking.table.supplier') }}</th>
                <th class="num">{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in items" :key="item.sku">
                <td><strong>{{ item.sku }}</strong></td>
                <td>{{ translateProductName(item.name) }}</td>
                <td>
                  <span :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span>
                </td>
                <td class="num">{{ item.quantity }}</td>
                <td class="num">{{ moneyExact(item.unit_cost) }}</td>
                <td class="num"><strong>{{ moneyExact(item.line_cost) }}</strong></td>
                <td>{{ item.supplier }}</td>
                <td class="num">{{ item.lead_time_days }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.budget-readout {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.budget-slider {
  width: 100%;
  accent-color: #0f172a;
}

.slider-scale {
  display: flex;
  justify-content: space-between;
  font-size: 0.813rem;
  color: #64748b;
  margin-top: 0.25rem;
}

.note {
  margin-top: 0.75rem;
  font-size: 0.813rem;
  color: #64748b;
}

.num {
  text-align: right;
}

.dimmed {
  opacity: 0.5;
  transition: opacity 0.15s ease;
}

.empty {
  text-align: center;
  padding: 2rem;
  color: #64748b;
  font-size: 0.938rem;
}

.place-order {
  background: #0f172a;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 0.5rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
}

.place-order:hover:not(:disabled) {
  background: #1e293b;
}

.place-order:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.success-banner {
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  color: #065f46;
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 1.25rem;
  font-size: 0.938rem;
}

.success-banner a {
  margin-left: 0.75rem;
  color: #2563eb;
  font-weight: 600;
}
</style>
