<template>
  <div class="campaign-overlay" v-if="visible" @click.self="close">
    <div class="campaign-modal">
      <div class="campaign-modal-header">
        <span class="campaign-title">{{ $t('campaign.title') }}</span>
        <button class="campaign-close" @click="close">×</button>
      </div>

      <!-- 步骤1：创建变体 -->
      <div class="campaign-body" v-if="!campaign">
        <p class="campaign-hint">{{ $t('campaign.hint') }}</p>

        <div class="variant-row" v-for="(v, i) in draftVariants" :key="i">
          <input
            class="variant-input label"
            v-model="v.label"
            :placeholder="$t('campaign.variantLabel')"
          />
          <input
            class="variant-input"
            v-model="v.replaceFrom"
            :placeholder="$t('campaign.replaceFrom')"
          />
          <span class="variant-arrow">→</span>
          <input
            class="variant-input"
            v-model="v.replaceTo"
            :placeholder="$t('campaign.replaceTo')"
          />
          <button class="variant-remove" @click="draftVariants.splice(i, 1)" v-if="draftVariants.length > 1">×</button>
        </div>

        <button class="campaign-add" @click="addVariant" :disabled="draftVariants.length >= 5">
          + {{ $t('campaign.addVariant') }}
        </button>

        <div class="campaign-footer">
          <span class="campaign-error" v-if="error">{{ error }}</span>
          <button class="campaign-btn primary" :disabled="creating || !canCreate" @click="handleCreate">
            <span v-if="creating" class="spinner"></span>
            {{ creating ? $t('campaign.creating') : $t('campaign.createBtn') }}
          </button>
        </div>
      </div>

      <!-- 步骤2：运行与对比 -->
      <div class="campaign-body" v-else>
        <div class="campaign-status-row">
          <span class="campaign-name">{{ campaign.name }}</span>
          <span class="campaign-state" :class="campaign.status">{{ campaignStatusLabel }}</span>
        </div>

        <table class="variant-table" v-if="comparison.summaries && comparison.summaries.length">
          <thead>
            <tr>
              <th>{{ $t('campaign.colVariant') }}</th>
              <th>{{ $t('campaign.colPosts') }}</th>
              <th>{{ $t('campaign.colComments') }}</th>
              <th>{{ $t('campaign.colSentiment') }}</th>
              <th>{{ $t('campaign.colIntent') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in comparison.summaries" :key="s.variant_id">
              <td>{{ s.label }}</td>
              <td>{{ s.posts }}</td>
              <td>{{ s.comments }}</td>
              <td>{{ s.sentiment_avg ?? '—' }}</td>
              <td>{{ s.purchase_intent_avg ?? '—' }}</td>
            </tr>
            <tr class="delta-row" v-for="d in (comparison.delta && comparison.delta.rows || [])" :key="'d' + d.variant_id">
              <td>Δ {{ d.label }}</td>
              <td :class="{ pos: d.posts_delta > 0, neg: d.posts_delta < 0 }">{{ d.posts_delta >= 0 ? '+' : '' }}{{ d.posts_delta }}</td>
              <td :class="{ pos: d.comments_delta > 0, neg: d.comments_delta < 0 }">{{ d.comments_delta >= 0 ? '+' : '' }}{{ d.comments_delta }}</td>
              <td>{{ d.sentiment_delta ?? '—' }}</td>
              <td>{{ d.purchase_intent_delta ?? '—' }}</td>
            </tr>
          </tbody>
        </table>

        <div class="campaign-progress" v-else>
          <div class="variant-status" v-for="(v, i) in campaign.variants" :key="v.variant_id">
            <span>{{ v.label }}</span>
            <span class="variant-state" :class="variantState(v)">{{ variantStateText(v) }}</span>
          </div>
        </div>

        <div class="campaign-report" v-if="comparisonReport">
          <div class="campaign-report-title">{{ $t('campaign.reportTitle') }}</div>
          <div class="campaign-report-body">{{ comparisonReport }}</div>
        </div>

        <div class="campaign-footer">
          <button class="campaign-btn" :disabled="isRunning" @click="handleRun" v-if="campaign.status !== 'running'">
            {{ $t('campaign.runBtn') }}
          </button>
          <button class="campaign-btn" :disabled="comparing" @click="handleComparison">
            {{ comparing ? $t('campaign.comparing') : $t('campaign.compareBtn') }}
          </button>
          <button class="campaign-btn primary" :disabled="generatingReport || !hasMetrics" @click="handleReport">
            <span v-if="generatingReport" class="spinner"></span>
            {{ generatingReport ? $t('campaign.generatingReport') : $t('campaign.reportBtn') }}
          </button>
        </div>
        <span class="campaign-error" v-if="error">{{ error }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  createCampaign,
  runCampaign,
  getCampaign,
  getCampaignComparison,
  generateCampaignReport
} from '../api/campaign'

const { t } = useI18n()

const props = defineProps({
  visible: Boolean,
  simulationId: String
})

const emit = defineEmits(['close'])

const draftVariants = ref([emptyVariant()])
const campaign = ref(null)
const comparison = ref({})
const comparisonReport = ref('')
const error = ref('')
const creating = ref(false)
const isRunning = ref(false)
const comparing = ref(false)
const generatingReport = ref(false)
let statusTimer = null

function emptyVariant() {
  return { label: '', replaceFrom: '', replaceTo: '' }
}

const canCreate = computed(() => {
  const filled = draftVariants.value.filter(v => v.label.trim())
  return filled.length > 0
})

const campaignStatusLabel = computed(() => {
  const map = {
    created: t('campaign.stateCreated'),
    running: t('campaign.stateRunning'),
    completed: t('campaign.stateCompleted'),
    failed: t('campaign.stateFailed')
  }
  return map[campaign.value?.status] || campaign.value?.status
})

const hasMetrics = computed(() => {
  return (comparison.value.summaries || []).some(s => s.posts > 0)
})

function addVariant() {
  draftVariants.value.push(emptyVariant())
}

function variantState(v) {
  return campaign.value?.run_status?.[v.simulation_id] || 'pending'
}

function variantStateText(v) {
  const state = variantState(v)
  const map = {
    pending: t('campaign.statePending'),
    running: t('campaign.stateRunning'),
    completed: t('campaign.stateCompleted'),
    stopped: t('campaign.stateStopped'),
    failed: t('campaign.stateFailed')
  }
  return map[state] || state
}

async function handleCreate() {
  error.value = ''
  creating.value = true
  try {
    const variants = draftVariants.value
      .filter(v => v.label.trim())
      .map(v => {
        const overrides = {}
        if (v.replaceFrom && v.replaceTo) {
          overrides.content_replacements = { [v.replaceFrom]: v.replaceTo }
        }
        return { label: v.label.trim(), overrides }
      })
    const res = await createCampaign({
      name: t('campaign.defaultName'),
      base_simulation_id: props.simulationId,
      variants
    })
    if (res.success && res.data) {
      campaign.value = res.data
      await handleRun()
    } else {
      error.value = res.error || t('common.unknownError')
    }
  } catch (err) {
    error.value = err.message
  } finally {
    creating.value = false
  }
}

async function handleRun() {
  error.value = ''
  try {
    const res = await runCampaign(campaign.value.campaign_id)
    if (res.success) {
      isRunning.value = true
      startPolling()
    } else {
      error.value = res.error || t('common.unknownError')
    }
  } catch (err) {
    error.value = err.message
  }
}

function startPolling() {
  stopPolling()
  statusTimer = setInterval(pollStatus, 8000)
  pollStatus()
}

function stopPolling() {
  if (statusTimer) {
    clearInterval(statusTimer)
    statusTimer = null
  }
}

async function pollStatus() {
  if (!campaign.value) return
  try {
    const res = await getCampaign(campaign.value.campaign_id)
    if (res.success && res.data) {
      campaign.value = res.data
      if (res.data.status === 'completed' || res.data.status === 'failed') {
        isRunning.value = false
        stopPolling()
        await handleComparison()
      }
    }
  } catch (err) {
    console.warn('Campaign 状态轮询失败:', err)
  }
}

async function handleComparison() {
  if (!campaign.value) return
  comparing.value = true
  try {
    const res = await getCampaignComparison(campaign.value.campaign_id)
    if (res.success && res.data) {
      comparison.value = res.data
    } else {
      error.value = res.error || t('common.unknownError')
    }
  } catch (err) {
    error.value = err.message
  } finally {
    comparing.value = false
  }
}

async function handleReport() {
  if (!campaign.value) return
  generatingReport.value = true
  error.value = ''
  try {
    const res = await generateCampaignReport(campaign.value.campaign_id)
    if (res.success && res.data) {
      comparisonReport.value = res.data.markdown
    } else {
      error.value = res.error || t('common.unknownError')
    }
  } catch (err) {
    error.value = err.message
  } finally {
    generatingReport.value = false
  }
}

function close() {
  stopPolling()
  emit('close')
}

watch(() => props.visible, (val) => {
  if (val) {
    draftVariants.value = [emptyVariant(), emptyVariant()]
    campaign.value = null
    comparison.value = {}
    comparisonReport.value = ''
    error.value = ''
  } else {
    stopPolling()
  }
})

onUnmounted(stopPolling)
</script>

<style scoped>
.campaign-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.campaign-modal {
  width: 640px;
  max-width: 92vw;
  max-height: 82vh;
  overflow-y: auto;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18);
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

.campaign-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid #EAEAEA;
}

.campaign-title {
  font-weight: 700;
  font-size: 15px;
}

.campaign-close {
  border: none;
  background: transparent;
  font-size: 20px;
  cursor: pointer;
  color: #999;
}

.campaign-body {
  padding: 16px 20px 20px;
}

.campaign-hint {
  font-size: 12px;
  color: #666;
  line-height: 1.6;
  margin: 0 0 12px;
}

.variant-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.variant-input {
  border: 1px solid #E5E5E5;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 12px;
  min-width: 0;
}

.variant-input.label {
  flex: 0 0 120px;
}

.variant-input:not(.label) {
  flex: 1;
}

.variant-arrow {
  color: #999;
}

.variant-remove {
  border: none;
  background: transparent;
  color: #c33;
  font-size: 16px;
  cursor: pointer;
}

.campaign-add {
  border: 1px dashed #ccc;
  background: transparent;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 12px;
  color: #666;
  cursor: pointer;
}

.campaign-footer {
  margin-top: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: flex-end;
}

.campaign-error {
  color: #d33;
  font-size: 12px;
}

.campaign-btn {
  border: 1px solid #E5E5E5;
  background: #fff;
  border-radius: 6px;
  padding: 7px 16px;
  font-size: 12px;
  cursor: pointer;
}

.campaign-btn.primary {
  background: #FF4500;
  border-color: #FF4500;
  color: #fff;
}

.campaign-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.spinner {
  display: inline-block;
  width: 11px;
  height: 11px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-right: 4px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.campaign-status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.campaign-name {
  font-weight: 600;
  font-size: 13px;
}

.campaign-state {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: #f2f2f2;
  color: #666;
}

.campaign-state.running { background: #fff4ec; color: #FF4500; }
.campaign-state.completed { background: #ecf7ee; color: #3a9d51; }
.campaign-state.failed { background: #fdeaea; color: #d33; }

.variant-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.variant-table th,
.variant-table td {
  border: 1px solid #eee;
  padding: 6px 8px;
  text-align: left;
}

.variant-table th {
  background: #fafafa;
  color: #666;
  font-weight: 600;
}

.delta-row td {
  color: #FF4500;
  background: #fffaf7;
}

.delta-row td.pos { color: #3a9d51; }
.delta-row td.neg { color: #d33; }

.campaign-progress {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.variant-status {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  padding: 6px 10px;
  border: 1px solid #eee;
  border-radius: 6px;
}

.variant-state.running { color: #FF4500; }
.variant-state.completed { color: #3a9d51; }
.variant-state.failed { color: #d33; }

.campaign-report {
  margin-top: 14px;
  border-top: 1px solid #eee;
  padding-top: 10px;
}

.campaign-report-title {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 6px;
}

.campaign-report-body {
  font-size: 12px;
  color: #333;
  line-height: 1.7;
  white-space: pre-wrap;
  background: #fafafa;
  border-radius: 8px;
  padding: 10px 12px;
}
</style>
