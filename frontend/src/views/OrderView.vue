<template>
  <div class="order-portal">
    <header class="portal-header">
      <div class="brand" @click="$router.push('/')"><svg width="20" height="20" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg" style="vertical-align:middle;margin-right:7px;flex-shrink:0"><rect width="32" height="32" rx="7" fill="#FF4500"/><line x1="8" y1="9" x2="14" y2="9" stroke="white" stroke-width="3" stroke-linecap="round" opacity="0.45"/><line x1="18" y1="9" x2="24" y2="9" stroke="white" stroke-width="3" stroke-linecap="round" opacity="0.45"/><line x1="8" y1="16" x2="24" y2="16" stroke="white" stroke-width="3" stroke-linecap="round" opacity="0.75"/><line x1="8" y1="23" x2="13" y2="23" stroke="white" stroke-width="3" stroke-linecap="round"/><line x1="19" y1="23" x2="24" y2="23" stroke="white" stroke-width="3" stroke-linecap="round"/></svg>YANCEVA</div>
      <div class="header-title">{{ $t('order.portalTitle') }}</div>
      <div class="header-actions">
        <LanguageSwitcher />
        <button class="back-btn" @click="$router.push('/')">{{ $t('order.backHome') }}</button>
      </div>
    </header>

    <main class="portal-body">
      <!-- 商品目录 + 表单 -->
      <section v-if="mode === 'catalog'" class="catalog-section">
        <h2 class="section-title">{{ $t('order.chooseProduct') }}</h2>
        <div class="product-grid">
          <button
            v-for="p in products" :key="p.product_id"
            class="product-card" :class="{ 'coming-soon': p.orderable === false }"
            :disabled="p.orderable === false"
            @click="p.orderable !== false && selectProduct(p)"
          >
            <div class="product-name">
              {{ p.name }}
              <span class="soon-badge" v-if="p.orderable === false">{{ $t('order.comingSoon') }}</span>
            </div>
            <div class="product-tagline">{{ p.tagline }}</div>
            <div class="product-foot" v-if="p.orderable !== false">
              <span class="price">${{ (p.price_cents / 100).toFixed(0) }}</span>
              <span class="cny-ref" v-if="locale === 'zh'">≈ ¥{{ Math.round(p.price_cents / 100 * 7.25) }}</span>
              <span class="sla">~{{ p.sla_minutes }}min</span>
            </div>
          </button>
        </div>
      </section>

      <section v-else-if="mode === 'form'" class="form-section">
        <h2 class="section-title">{{ selectedProduct.name }}</h2>
        <p class="section-sub">{{ selectedProduct.tagline }}</p>

        <div class="form-grid">
          <div class="form-field" v-for="(schema, key) in (selectedProduct.intake_schema.properties || {})" :key="key">
            <label :class="{ required: isRequired(key) }">{{ schema.title || key }}</label>
            <textarea
              v-if="schema.type === 'text'"
              v-model="form[key]" rows="4"
              class="auto-grow"
              :placeholder="schema.placeholder || ''"
              @input="autoResize($event)"
            ></textarea>
            <input
              v-else v-model="form[key]"
              :placeholder="schema.placeholder || ''"
            />
          </div>
          <div class="form-field">
            <label>{{ $t('order.contactEmail') }}</label>
            <input v-model="userEmail" type="email" placeholder="you@example.com" />
          </div>
          <div class="form-field">
            <label>{{ $t('order.reportLanguage') }}</label>
            <select v-model="language" class="lang-select">
              <option value="zh">中文报告</option>
              <option value="en">English Report</option>
            </select>
          </div>
          <div class="form-field span2">
            <label>{{ $t('order.seedFiles') }}</label>
            <input type="file" multiple accept=".pdf,.md,.txt" @change="onFiles" />
            <div class="file-hint">{{ $t('order.seedFilesHint') }}</div>
          </div>
        </div>

        <div class="form-actions">
          <button class="ghost-btn" @click="mode = 'catalog'">{{ $t('order.back') }}</button>
          <button class="primary-btn" :disabled="submitting || !canSubmit" @click="submitOrder">
            <span v-if="submitting" class="spinner"></span>
            {{ submitting ? $t('order.submitting') : $t('order.submitAndPay', { price: priceText }) }}
          </button>
        </div>
        <div class="error" v-if="error">{{ error }}</div>
      </section>

      <!-- 订单详情 / 进度 -->
      <section v-else class="detail-section">
        <h2 class="section-title">{{ order.title || order.order_id }}</h2>
        <div class="status-row">
          <span class="status-badge" :class="order.status">{{ statusText(order.status) }}</span>
          <span class="order-meta">{{ order.product_name || order.product_id }} · {{ order.created_at }}</span>
        </div>

        <div class="progress-bar-wrap" v-if="!isTerminal">
          <div class="progress-bar"><div class="progress-fill" :style="{ width: order.progress + '%' }"></div></div>
          <div class="progress-stage" v-for="(v, k) in (order.stage_detail || {})" :key="k">
            <span class="stage-key">{{ k }}</span>: <span class="stage-val">{{ stageText(v) }}</span>
          </div>
        </div>

        <div class="result-box" v-if="order.status === 'SUCCEEDED'">
          <h3>{{ $t('order.deliverableReady') }}</h3>
          <div class="metric-chips">
            <span class="chip">{{ $t('order.chipPosts') }}: {{ metricTotals.posts }}</span>
            <span class="chip">{{ $t('order.chipComments') }}: {{ metricTotals.comments }}</span>
            <span class="chip">{{ $t('order.chipRounds') }}: {{ metricTotals.rounds }}</span>
          </div>
          <div class="result-actions">
            <a class="primary-btn" :href="deliverableUrl(order.order_id)" target="_blank">
              {{ $t('order.downloadDeliverable') }}
            </a>
            <button class="ghost-btn" v-if="order.result && order.result.report_url"
                    @click="openReport(order.result.report_url)">
              {{ $t('order.viewOnlineReport') }}
            </button>
            <button class="ghost-btn" @click="resetToCatalog">{{ $t('order.newOrder') }}</button>
          </div>
        </div>

        <div class="error" v-if="order.status === 'FAILED'">{{ order.error }}</div>

        <div class="form-actions" v-if="!isTerminal && order.status === 'PENDING_PAYMENT'">
          <button class="primary-btn" @click="pay">{{ $t('order.payNow') }}</button>
          <button class="ghost-btn" @click="doCancel">{{ $t('order.cancel') }}</button>
        </div>
        <div class="form-actions" v-if="order.status === 'RUNNING' || order.status === 'ASSIGNED'">
          <button class="ghost-btn" @click="doCancel">{{ $t('order.cancelRunning') }}</button>
        </div>
      </section>

      <!-- 我的订单 -->
      <section class="orders-list" v-if="mode !== 'detail' && orders.length">
        <h2 class="section-title">{{ $t('order.myOrders') }}</h2>
        <div class="order-row" v-for="o in orders" :key="o.order_id" @click="openDetail(o.order_id)">
          <span class="row-title">{{ o.title }}</span>
          <span class="status-badge small" :class="o.status">{{ statusText(o.status) }}</span>
          <span class="row-progress" v-if="!isTerminalStatus(o.status)">{{ o.progress }}%</span>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import LanguageSwitcher from '../components/LanguageSwitcher.vue'
import {
  listProducts, createOrder, listOrders, getOrder, payOrder, cancelOrder, deliverableUrl
} from '../api/orders'

const { t, locale } = useI18n()
const router = useRouter()

const mode = ref('catalog')
const products = ref([])
const orders = ref([])
const selectedProduct = ref(null)
const form = ref({})
const files = ref([])
const userEmail = ref(localStorage.getItem('order_email') || '')
const language = ref(localStorage.getItem('order_language') || locale.value)
const order = ref(null)
const error = ref('')
const submitting = ref(false)
let pollTimer = null

const canSubmit = computed(() => {
  if (!selectedProduct.value || !userEmail.value.includes('@')) return false
  const required = selectedProduct.value.intake_schema?.required || []
  return required.every(key => String(form.value[key] || '').trim())
})

const priceText = computed(() =>
  selectedProduct.value ? `$${(selectedProduct.value.price_cents / 100).toFixed(0)}` : '')

const isTerminal = computed(() =>
  ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(order.value?.status))

const metricTotals = computed(() => order.value?.result?.metrics_summary?.totals || {})

function isRequired(key) {
  return (selectedProduct.value?.intake_schema?.required || []).includes(key)
}

function selectProduct(p) {
  selectedProduct.value = p
  form.value = {}
  error.value = ''
  mode.value = 'form'
  // 渲染后按 placeholder/内容自适应 textarea 高度
  nextTick(() => {
    document.querySelectorAll('.form-field textarea.auto-grow').forEach(autoResizeEl)
  })
}

// textarea 自适应高度：随内容增长，不低于初始高度
function autoResizeEl(el) {
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.max(el.scrollHeight, 96) + 'px'
}

function autoResize(event) {
  autoResizeEl(event.target)
}

function onFiles(event) {
  files.value = Array.from(event.target.files || [])
}

async function submitOrder() {
  error.value = ''
  submitting.value = true
  try {
    const fd = new FormData()
    fd.append('product_id', selectedProduct.value.product_id)
    fd.append('user_email', userEmail.value)
    fd.append('title', `${selectedProduct.value.name} · ${form.value.product_name || ''}`)
    fd.append('payload', JSON.stringify({ ...form.value, language: language.value }))
    files.value.forEach(f => fd.append('files', f))
    const res = await createOrder(fd)
    if (res.success && res.data) {
      localStorage.setItem('order_email', userEmail.value)
      localStorage.setItem('order_language', language.value)
      order.value = res.data
      mode.value = 'detail'
      if (res.data.checkout_url) {
        window.location.href = res.data.checkout_url
        return
      }
      await tryAutoPay()
      startPolling()
    } else {
      error.value = res.error || t('common.unknownError')
    }
  } catch (err) {
    error.value = err.message
  } finally {
    submitting.value = false
  }
}

async function tryAutoPay() {
  if (!order.value) return
  try {
    const res = await payOrder(order.value.order_id)
    if (res.success && res.data?.checkout_url) {
      window.location.href = res.data.checkout_url
    } else if (res.success) {
      await refreshOrder()
    } else {
      error.value = res.error || t('common.unknownError')
    }
  } catch (err) {
    error.value = err.message
  }
}

async function pay() {
  error.value = ''
  try {
    const res = await payOrder(order.value.order_id)
    if (res.success && res.data?.checkout_url) {
      window.location.href = res.data.checkout_url
    } else if (res.success) {
      await refreshOrder()
    } else {
      error.value = res.error || t('common.unknownError')
    }
  } catch (err) {
    error.value = err.message
  }
}

async function doCancel() {
  try {
    await cancelOrder(order.value.order_id)
    await refreshOrder()
  } catch (err) {
    error.value = err.message
  }
}

function openReport(reportUrl) {
  const reportId = (reportUrl || '').split('/').pop()
  if (reportId) router.push({ name: 'Report', params: { reportId } })
}

function resetToCatalog() {
  stopPolling()
  mode.value = 'catalog'
  order.value = null
  loadOrders()
}

async function refreshOrder() {
  if (!order.value) return
  const res = await getOrder(order.value.order_id)
  if (res.success && res.data) order.value = res.data
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    await refreshOrder()
    if (isTerminal.value) stopPolling()
  }, 5000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

async function openDetail(orderId) {
  const res = await getOrder(orderId)
  if (res.success && res.data) {
    order.value = res.data
    mode.value = 'detail'
    if (!isTerminal.value) startPolling()
  }
}

async function loadOrders() {
  const email = localStorage.getItem('order_email')
  const res = await listOrders(email ? { user_email: email } : {})
  if (res.success && res.data) orders.value = res.data
}

function statusText(status) {
  const map = {
    PENDING_PAYMENT: t('order.stPendingPayment'),
    QUEUED: t('order.stQueued'),
    ASSIGNED: t('order.stAssigned'),
    RUNNING: t('order.stRunning'),
    SUCCEEDED: t('order.stSucceeded'),
    FAILED: t('order.stFailed'),
    CANCELLED: t('order.stCancelled'),
  }
  return map[status] || status
}

function isTerminalStatus(status) {
  return ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(status)
}

function stageText(value) {
  if (typeof value === 'string') return value
  if (value && typeof value === 'object') return JSON.stringify(value).slice(0, 120)
  return String(value)
}

async function loadProducts() {
  const res = await listProducts({ include_upcoming: true })
  if (res.success && res.data) products.value = res.data
}

// 切换语言后按新语言重新拉取商品目录，并同步当前选中的商品（表单标题/表单 schema 跟随语言）
watch(locale, async () => {
  await loadProducts()
  if (selectedProduct.value) {
    const updated = products.value.find(
      p => p.product_id === selectedProduct.value.product_id
    )
    if (updated) selectedProduct.value = updated
  }
})

onMounted(async () => {
  await loadProducts()
  loadOrders()
  // 支付回跳：URL 带 order_id（&paid=1）→ 直接恢复该订单的进度页
  const params = new URLSearchParams(window.location.search)
  const returnOrderId = params.get('order_id')
  if (returnOrderId) {
    const r = await getOrder(returnOrderId)
    if (r.success && r.data) {
      order.value = r.data
      mode.value = 'detail'
      if (!isTerminal.value) startPolling()
    }
  }
})

onUnmounted(stopPolling)
</script>

<style scoped>
.order-portal {
  min-height: 100vh;
  background: #fff;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

.portal-header {
  display: flex; align-items: center; gap: 20px;
  padding: 16px 28px; border-bottom: 1px solid #EAEAEA;
}
.brand { font-weight: 800; letter-spacing: 2px; cursor: pointer; color: #FF4500; }
.header-title { font-size: 15px; font-weight: 700; flex: 1; }
.header-actions { display: flex; align-items: center; gap: 12px; }
.back-btn {
  border: 1px solid #E5E5E5; background: #fff; border-radius: 6px;
  padding: 6px 14px; font-size: 12px; cursor: pointer;
}

.portal-body { max-width: 880px; margin: 0 auto; padding: 32px 24px 80px; }
.section-title { font-size: 20px; margin: 0 0 6px; }
.section-sub { color: #666; font-size: 13px; margin: 0 0 20px; }

.product-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
.product-card {
  text-align: left; border: 1px solid #E5E5E5; border-radius: 12px;
  padding: 16px; cursor: pointer; background: #fff; transition: border-color .15s;
  display: flex; flex-direction: column; gap: 8px;
}
.product-card:hover { border-color: #FF4500; }
.product-name { font-weight: 700; font-size: 15px; }
.product-tagline { font-size: 12px; color: #666; line-height: 1.6; flex: 1; }
.product-foot { display: flex; justify-content: space-between; align-items: center; }
.price { color: #FF4500; font-weight: 800; font-size: 18px; }
.cny-ref { font-size: 12px; color: #999; margin-left: 4px; }
.sla { color: #999; font-size: 11px; }
.coming-note { color: #aaa; font-size: 12px; margin-top: 16px; }
.product-card.coming-soon { opacity: 0.55; cursor: default; background: #fafafa; }
.soon-badge {
  font-size: 10px; padding: 2px 8px; border-radius: 10px;
  background: #f0f0f0; color: #888; font-weight: 500; vertical-align: middle;
}

.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 16px 0; }
.form-field { display: flex; flex-direction: column; gap: 4px; }
.form-field.span2 { grid-column: span 2; }
.form-field label { font-size: 12px; color: #444; }
.form-field label.required::after { content: ' *'; color: #FF4500; }
.form-field input, .form-field textarea {
  border: 1px solid #E5E5E5; border-radius: 8px; padding: 8px 12px;
  font-size: 13px; font-family: inherit;
}
.form-field textarea {
  min-height: 110px; max-height: 420px; resize: vertical;
  line-height: 1.6; overflow-y: auto; width: 100%;
}
.form-field input:focus, .form-field textarea:focus { outline: none; border-color: #FF4500; }
.file-hint { font-size: 11px; color: #999; }
.lang-select { border: 1px solid #E5E5E5; border-radius: 8px; padding: 8px 12px; font-size: 13px; }

.form-actions { display: flex; gap: 10px; margin-top: 18px; }
.primary-btn {
  background: #FF4500; color: #fff; border: none; border-radius: 8px;
  padding: 10px 22px; font-size: 13px; font-weight: 600; cursor: pointer;
  text-decoration: none; display: inline-flex; align-items: center; gap: 6px;
}
.primary-btn:disabled { opacity: .5; cursor: not-allowed; }
.ghost-btn {
  border: 1px solid #E5E5E5; background: #fff; border-radius: 8px;
  padding: 10px 18px; font-size: 13px; cursor: pointer;
}
.spinner {
  width: 12px; height: 12px; border: 2px solid rgba(255,255,255,.4);
  border-top-color: #fff; border-radius: 50%; animation: spin .8s linear infinite;
  display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }
.error { color: #d33; font-size: 13px; margin-top: 10px; }

.status-row { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.status-badge {
  font-size: 12px; padding: 3px 10px; border-radius: 12px; background: #f2f2f2; color: #555;
}
.status-badge.SUCCEEDED { background: #ecf7ee; color: #3a9d51; }
.status-badge.RUNNING, .status-badge.ASSIGNED { background: #fff4ec; color: #FF4500; }
.status-badge.FAILED { background: #fdeaea; color: #d33; }
.status-badge.CANCELLED { background: #eee; color: #999; }
.status-badge.small { font-size: 11px; }
.order-meta { color: #999; font-size: 12px; }

.progress-bar-wrap { margin: 18px 0; }
.progress-bar { height: 10px; background: #f0f0f0; border-radius: 6px; overflow: hidden; }
.progress-fill { height: 100%; background: #FF4500; border-radius: 6px; transition: width .5s; }
.progress-stage { font-size: 12px; color: #666; margin-top: 6px; }
.stage-key { font-family: 'JetBrains Mono', monospace; color: #FF4500; }

.result-box { border: 1px solid #e5e5e5; border-radius: 12px; padding: 18px; background: #fafafa; }
.result-box h3 { margin: 0 0 10px; }
.metric-chips { display: flex; gap: 8px; margin-bottom: 14px; }
.chip {
  font-size: 12px; background: #fff; border: 1px solid #E5E5E5;
  border-radius: 12px; padding: 3px 10px;
}
.result-actions { display: flex; gap: 10px; flex-wrap: wrap; }

.orders-list { margin-top: 48px; }
.order-row {
  display: flex; align-items: center; gap: 12px;
  border: 1px solid #eee; border-radius: 10px; padding: 10px 14px;
  margin-bottom: 8px; cursor: pointer; font-size: 13px;
}
.order-row:hover { border-color: #FF4500; }
.row-title { flex: 1; font-weight: 600; }
.row-progress { color: #FF4500; font-family: 'JetBrains Mono', monospace; }
</style>
