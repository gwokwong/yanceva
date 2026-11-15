<template>
  <div class="cookie-banner" v-if="show" role="dialog" aria-label="Cookie consent">
    <div class="cookie-inner">
      <p class="cookie-text">
        {{ $t('cookie.text') }}
        <router-link to="/privacy" class="cookie-link">{{ $t('cookie.privacyLink') }}</router-link>
      </p>
      <div class="cookie-actions">
        <button class="cookie-btn ghost" @click="consent(false)">{{ $t('cookie.decline') }}</button>
        <button class="cookie-btn solid" @click="consent(true)">{{ $t('cookie.accept') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

const { locale } = useI18n()
const show = ref(false)

onMounted(() => {
  // 已有明确选择则不再弹出；新访客延迟 1.5s 弹出（不挡首屏）
  const saved = localStorage.getItem('cookie_consent')
  if (!saved) {
    setTimeout(() => { show.value = true }, 1500)
  }
})

function consent(accepted) {
  localStorage.setItem('cookie_consent', accepted ? 'all' : 'essential')
  localStorage.setItem('cookie_consent_at', new Date().toISOString())
  show.value = false
}
</script>

<style scoped>
.cookie-banner {
  position: fixed; left: 0; right: 0; bottom: 0; z-index: 2000;
  background: rgba(20, 20, 20, 0.96); color: #eee;
}
.cookie-inner {
  max-width: 880px; margin: 0 auto; padding: 16px 24px;
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
}
.cookie-text { flex: 1; min-width: 260px; font-size: 13px; line-height: 1.6; margin: 0; }
.cookie-link { color: #FF9B6A; text-decoration: underline; }
.cookie-actions { display: flex; gap: 10px; }
.cookie-btn { border-radius: 6px; padding: 8px 18px; font-size: 13px; cursor: pointer; }
.cookie-btn.ghost { background: transparent; border: 1px solid #666; color: #ccc; }
.cookie-btn.solid { background: #FF4500; border: 1px solid #FF4500; color: #fff; font-weight: 600; }
</style>
