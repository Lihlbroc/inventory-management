<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="isOpen && backlogItem" class="modal-overlay" @click="close">
        <div class="modal-container" @click.stop>
          <div class="modal-header">
            <h3 class="modal-title">
              {{ mode === 'view' ? 'Purchase Order' : 'Create Purchase Order' }}
            </h3>
            <button class="close-button" aria-label="Close" @click="close">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path
                  d="M15 5L5 15M5 5L15 15"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                />
              </svg>
            </button>
          </div>

          <div class="modal-body">
            <div class="item-context">
              <h4 class="item-name">{{ backlogItem.item_name }}</h4>
              <div class="context-grid">
                <div class="info-item">
                  <div class="info-label">SKU</div>
                  <div class="info-value mono">{{ backlogItem.item_sku }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">Order ID</div>
                  <div class="info-value mono">{{ backlogItem.order_id }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">Shortfall</div>
                  <div class="info-value shortfall">{{ shortfall }} units</div>
                </div>
              </div>
            </div>

            <!-- CREATE MODE -->
            <form
              v-if="mode !== 'view'"
              id="po-form"
              class="po-form"
              novalidate
              @submit.prevent="submit"
            >
              <div class="form-group">
                <label for="po-supplier">Supplier Name</label>
                <input
                  id="po-supplier"
                  v-model="form.supplier_name"
                  type="text"
                  required
                  :disabled="submitting"
                />
              </div>

              <div class="form-row">
                <div class="form-group">
                  <label for="po-quantity">Quantity</label>
                  <input
                    id="po-quantity"
                    v-model.number="form.quantity"
                    type="number"
                    min="1"
                    step="1"
                    required
                    :disabled="submitting"
                  />
                </div>
                <div class="form-group">
                  <label for="po-unit-cost">Unit Cost (USD)</label>
                  <input
                    id="po-unit-cost"
                    v-model.number="form.unit_cost"
                    type="number"
                    min="0"
                    step="0.01"
                    required
                    :disabled="submitting"
                  />
                </div>
              </div>

              <div class="form-group">
                <label for="po-date">Expected Delivery Date</label>
                <input
                  id="po-date"
                  v-model="form.expected_delivery_date"
                  type="date"
                  :min="today"
                  required
                  :disabled="submitting"
                />
              </div>

              <div class="form-group">
                <label for="po-notes">Notes (optional)</label>
                <textarea
                  id="po-notes"
                  v-model="form.notes"
                  rows="3"
                  :disabled="submitting"
                ></textarea>
              </div>

              <div class="total-row">
                <span class="info-label">Total Cost</span>
                <span class="total-value">{{ formatMoney(formTotal) }}</span>
              </div>

              <div v-if="submitError" class="error-message" role="alert">
                {{ submitError }}
              </div>
            </form>

            <!-- VIEW MODE -->
            <div v-else>
              <div v-if="loading" class="state-message">
                Loading purchase order...
              </div>
              <div v-else-if="loadError" class="error-message" role="alert">
                {{ loadError }}
              </div>
              <div v-else-if="purchaseOrder" class="info-grid">
                <div class="info-item">
                  <div class="info-label">PO ID</div>
                  <div class="info-value mono">{{ purchaseOrder.id }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">Status</div>
                  <div class="info-value">
                    <span class="badge" :class="statusClass">
                      {{ purchaseOrder.status }}
                    </span>
                  </div>
                </div>
                <div class="info-item">
                  <div class="info-label">Supplier</div>
                  <div class="info-value">
                    {{ purchaseOrder.supplier_name }}
                  </div>
                </div>
                <div class="info-item">
                  <div class="info-label">Quantity</div>
                  <div class="info-value">
                    {{ purchaseOrder.quantity }} units
                  </div>
                </div>
                <div class="info-item">
                  <div class="info-label">Unit Cost</div>
                  <div class="info-value">
                    {{ formatMoney(purchaseOrder.unit_cost) }}
                  </div>
                </div>
                <div class="info-item">
                  <div class="info-label">Total Cost</div>
                  <div class="info-value">{{ formatMoney(poTotal) }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">Expected Delivery</div>
                  <div class="info-value">
                    {{ formatDate(purchaseOrder.expected_delivery_date) }}
                  </div>
                </div>
                <div class="info-item">
                  <div class="info-label">Created</div>
                  <div class="info-value">
                    {{ formatDate(purchaseOrder.created_date) }}
                  </div>
                </div>
                <div class="info-item full-width">
                  <div class="info-label">Notes</div>
                  <div class="info-value notes">
                    {{ purchaseOrder.notes || 'None' }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <button
              type="button"
              class="btn-secondary"
              :disabled="submitting"
              @click="close"
            >
              {{ mode === 'view' ? 'Close' : 'Cancel' }}
            </button>
            <button
              v-if="mode !== 'view'"
              type="submit"
              form="po-form"
              class="btn-primary"
              :disabled="!isValid || submitting"
            >
              {{ submitting ? 'Creating...' : 'Create Purchase Order' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script>
import { ref, reactive, computed, watch, onBeforeUnmount } from 'vue'
import { api } from '../api'
import { formatCurrencyWithDecimals } from '../utils/currency'

// Local YYYY-MM-DD (toISOString would shift to UTC and can yield tomorrow/yesterday)
const toDateInputValue = (d) => {
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

export default {
  name: 'PurchaseOrderModal',
  props: {
    isOpen: { type: Boolean, default: false },
    backlogItem: { type: Object, default: null },
    mode: {
      type: String,
      default: 'create',
      validator: (v) => ['create', 'view'].includes(v)
    }
  },
  emits: ['close', 'po-created'],
  setup(props, { emit }) {
    const form = reactive({
      supplier_name: '',
      quantity: 1,
      unit_cost: 0,
      expected_delivery_date: '',
      notes: ''
    })
    const submitting = ref(false)
    const submitError = ref(null)

    const purchaseOrder = ref(null)
    const loading = ref(false)
    const loadError = ref(null)

    const today = computed(() => toDateInputValue(new Date()))

    const shortfall = computed(() => {
      if (!props.backlogItem) return 0
      return Math.max(
        props.backlogItem.quantity_needed -
          props.backlogItem.quantity_available,
        0
      )
    })

    const formTotal = computed(() => {
      const q = Number(form.quantity)
      const c = Number(form.unit_cost)
      if (!Number.isFinite(q) || !Number.isFinite(c)) return 0
      return q * c
    })

    const poTotal = computed(() => {
      if (!purchaseOrder.value) return 0
      return purchaseOrder.value.quantity * purchaseOrder.value.unit_cost
    })

    const isValid = computed(() => {
      const q = form.quantity
      const c = form.unit_cost
      // v-model.number yields '' for an emptied input
      if (!form.supplier_name.trim()) return false
      if (typeof q !== 'number' || !Number.isInteger(q) || q <= 0) return false
      if (typeof c !== 'number' || !Number.isFinite(c) || c < 0) return false
      const d = form.expected_delivery_date
      if (!d) return false
      const parsed = new Date(`${d}T00:00:00`)
      if (isNaN(parsed.getTime())) return false
      return d >= today.value
    })

    const statusClass = computed(() => {
      const s = (purchaseOrder.value?.status || '').toLowerCase()
      if (s === 'pending') return 'warning'
      if (s === 'received' || s === 'delivered') return 'success'
      if (s === 'cancelled') return 'danger'
      return 'info'
    })

    const formatMoney = (value) => formatCurrencyWithDecimals(value, 'USD', 2)

    const formatDate = (value) => {
      if (!value) return 'N/A'
      // Date-only strings are parsed as UTC; pin to local midnight to avoid off-by-one
      const str = /^\d{4}-\d{2}-\d{2}$/.test(value)
        ? `${value}T00:00:00`
        : value
      const date = new Date(str)
      if (isNaN(date.getTime())) return 'N/A'
      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      })
    }

    const resetForm = () => {
      form.supplier_name = ''
      form.quantity = Math.max(shortfall.value, 1)
      form.unit_cost = 0
      form.expected_delivery_date = ''
      form.notes = ''
      submitting.value = false
      submitError.value = null
    }

    // Incremented per request so a slow response for a previous item is ignored
    let loadToken = 0
    const loadPurchaseOrder = async () => {
      const token = ++loadToken
      purchaseOrder.value = null
      loadError.value = null
      if (!props.backlogItem) {
        loading.value = false
        return
      }
      loading.value = true
      try {
        const data = await api.getPurchaseOrderByBacklogItem(
          props.backlogItem.id
        )
        if (token !== loadToken) return
        purchaseOrder.value = data
      } catch (err) {
        if (token !== loadToken) return
        loadError.value =
          err.response?.status === 404
            ? 'No purchase order found for this item.'
            : 'Failed to load purchase order.'
        if (err.response?.status !== 404) console.error('PO load error:', err)
      } finally {
        if (token === loadToken) loading.value = false
      }
    }

    const submit = async () => {
      if (!isValid.value || submitting.value || !props.backlogItem) return
      submitting.value = true
      submitError.value = null
      try {
        const payload = {
          backlog_item_id: props.backlogItem.id,
          supplier_name: form.supplier_name.trim(),
          quantity: form.quantity,
          unit_cost: form.unit_cost,
          expected_delivery_date: form.expected_delivery_date
        }
        const notes = form.notes.trim()
        if (notes) payload.notes = notes
        const po = await api.createPurchaseOrder(payload)
        emit('po-created', po)
      } catch (err) {
        console.error('PO create error:', err)
        const detail = err.response?.data?.detail
        submitError.value =
          typeof detail === 'string' && detail
            ? detail
            : 'Failed to create purchase order. Please try again.'
      } finally {
        submitting.value = false
      }
    }

    const close = () => emit('close')

    const onKeydown = (e) => {
      if (e.key === 'Escape') close()
    }

    const syncOnOpen = () => {
      if (props.mode === 'view') {
        loadPurchaseOrder()
      } else {
        resetForm()
      }
    }

    watch(
      () => [props.isOpen, props.backlogItem, props.mode],
      ([open]) => {
        if (open) {
          syncOnOpen()
          document.addEventListener('keydown', onKeydown)
        } else {
          loadToken++ // drop any in-flight view request
          document.removeEventListener('keydown', onKeydown)
        }
      },
      { immediate: true }
    )

    onBeforeUnmount(() => {
      document.removeEventListener('keydown', onKeydown)
    })

    return {
      form,
      submitting,
      submitError,
      purchaseOrder,
      loading,
      loadError,
      today,
      shortfall,
      formTotal,
      poTotal,
      isValid,
      statusClass,
      formatMoney,
      formatDate,
      submit,
      close
    }
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  padding: 1rem;
}

.modal-container {
  background: white;
  border-radius: 12px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15);
  max-width: 600px;
  width: 100%;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.modal-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.close-button {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.15s ease;
}

.close-button:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem 2rem;
}

.item-context {
  padding-bottom: 1.25rem;
  margin-bottom: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.item-name {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  margin: 0 0 1rem 0;
}

.context-grid,
.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 1.25rem;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 0;
}

.info-item.full-width {
  grid-column: 1 / -1;
}

.info-label,
.form-group label {
  font-size: 0.813rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.info-value {
  font-size: 0.938rem;
  color: #0f172a;
  font-weight: 500;
  overflow-wrap: anywhere;
}

.info-value.mono {
  font-family: 'Monaco', 'Courier New', monospace;
  color: #2563eb;
}

.info-value.shortfall {
  color: #dc2626;
  font-weight: 700;
}

.info-value.notes {
  white-space: pre-wrap;
}

.po-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.form-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-group input,
.form-group textarea {
  padding: 0.625rem 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 0.938rem;
  font-family: inherit;
  color: #0f172a;
  background: white;
  transition: all 0.15s ease;
}

.form-group textarea {
  resize: vertical;
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
}

.form-group input:disabled,
.form-group textarea:disabled {
  background: #f8fafc;
  color: #64748b;
}

.total-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}

.total-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
}

.state-message {
  padding: 2rem 0;
  text-align: center;
  color: #64748b;
}

.error-message {
  padding: 0.75rem 1rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #991b1b;
  font-size: 0.875rem;
}

.badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 6px;
  font-size: 0.813rem;
  font-weight: 600;
}

.badge.warning {
  background: #fef3c7;
  color: #92400e;
}

.badge.success {
  background: #dcfce7;
  color: #166534;
}

.badge.danger {
  background: #fecaca;
  color: #991b1b;
}

.badge.info {
  background: #dbeafe;
  color: #1e40af;
}

.modal-footer {
  padding: 1.5rem;
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.btn-secondary,
.btn-primary {
  padding: 0.625rem 1.25rem;
  border-radius: 8px;
  font-weight: 500;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-secondary {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  color: #334155;
}

.btn-secondary:hover:not(:disabled) {
  background: #e2e8f0;
  border-color: #cbd5e1;
}

.btn-primary {
  background: #2563eb;
  border: 1px solid #2563eb;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
  border-color: #1d4ed8;
}

.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Modal transition animations */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal-container,
.modal-leave-active .modal-container {
  transition: transform 0.2s ease;
}

.modal-enter-from .modal-container,
.modal-leave-to .modal-container {
  transform: scale(0.95);
}

@media (max-width: 520px) {
  .form-row {
    grid-template-columns: 1fr;
  }
}
</style>
