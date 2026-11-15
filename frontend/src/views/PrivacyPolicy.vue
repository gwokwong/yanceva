<template>
  <div class="legal-page">
    <header class="legal-header">
      <div class="brand" @click="$router.push('/')"><svg width="20" height="20" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg" style="vertical-align:middle;margin-right:7px;flex-shrink:0"><rect width="32" height="32" rx="7" fill="#FF4500"/><line x1="8" y1="9" x2="14" y2="9" stroke="white" stroke-width="3" stroke-linecap="round" opacity="0.45"/><line x1="18" y1="9" x2="24" y2="9" stroke="white" stroke-width="3" stroke-linecap="round" opacity="0.45"/><line x1="8" y1="16" x2="24" y2="16" stroke="white" stroke-width="3" stroke-linecap="round" opacity="0.75"/><line x1="8" y1="23" x2="13" y2="23" stroke="white" stroke-width="3" stroke-linecap="round"/><line x1="19" y1="23" x2="24" y2="23" stroke="white" stroke-width="3" stroke-linecap="round"/></svg>YANCEVA</div>
      <LanguageSwitcher />
    </header>
    <main class="legal-body">
      <!-- eslint-disable-next-line vue/no-v-html — 本地受控内容 -->
      <div v-html="content"></div>
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import LanguageSwitcher from '../components/LanguageSwitcher.vue'

const { locale } = useI18n()

// ⚠️ 模板性质文本，上线前建议由法务复核
const CONTENT = {
  en: {
    title: 'Privacy Policy',
    updated: 'Last updated: 2026-11-15',
    sections: [
      ['1. What we collect', `
        <p>When you use our rehearsal services we collect: your contact email (for order delivery),
        the seed files and form content you upload (product descriptions, competitor notes),
        order records (product, timestamps, payment reference from our payment provider), and
        the simulation artifacts generated for your order.</p>
        <p>We also store a small preference in your browser's localStorage: language choice and
        your cookie-consent decision. We do not use third-party advertising or tracking cookies.</p>`],
      ['2. How your data is processed', `
        <p>Your uploaded materials and form inputs are sent to our LLM provider (DeepSeek API)
        to run the simulation, under their API data policy which states customer data is not used
        for model training. Payments are processed by our Merchant of Record (Creem); we never
        see your full card details. Simulation agents are fictional personas generated from your
        inputs — they are not real people.</p>`],
      ['3. Retention & deletion', `
        <p>Order records and deliverables are retained while your account is active and for
        bookkeeping purposes. You may request deletion of your order data and uploaded files at
        any time via the contact email below; we will delete them within 30 days.</p>`],
      ['4. Your rights', `
        <p>Depending on your jurisdiction (e.g. GDPR for EU residents) you have the right to
        access, correct, export and delete your personal data, and to object to processing.
        Contact us at the email below to exercise these rights.</p>`],
      ['5. Contact', `<p>Questions about this policy: support@example.com</p>`],
    ],
  },
  zh: {
    title: '隐私政策',
    updated: '最后更新：2026-11-15',
    sections: [
      ['1. 我们收集什么', `
        <p>使用预演服务时，我们收集：您的联系邮箱（用于交付订单）、您上传的种子资料与表单内容
        （产品描述、竞品信息等）、订单记录（商品、时间、支付渠道返回的支付参考号），以及为该订单
        生成的推演产物。</p>
        <p>我们还会在您的浏览器 localStorage 中保存少量偏好：语言选择与 Cookie 同意决定。
        我们不使用第三方广告或追踪 Cookie。</p>`],
      ['2. 数据如何被处理', `
        <p>您上传的资料与表单内容会发送给我们的 LLM 服务商（DeepSeek API）用于运行推演，
        其 API 数据政策承诺客户数据不用于模型训练。支付由我们的名义卖家（Merchant of Record：
        Creem）处理，我们不会接触您的完整银行卡信息。推演中的 Agent 是根据您的输入生成的
        虚构角色，并非真实人物。</p>`],
      ['3. 保存与删除', `
        <p>订单记录与交付物在服务有效期内保存以备查。您可以随时通过下方联系邮箱要求删除
        您的订单数据与上传文件，我们将在 30 天内完成删除。</p>`],
      ['4. 您的权利', `
        <p>根据您所在司法辖区（如欧盟 GDPR），您有权访问、更正、导出和删除您的个人数据，
        并有权拒绝特定处理。通过下方邮箱联系我们即可行使这些权利。</p>`],
      ['5. 联系我们', `<p>关于本政策的疑问：support@example.com</p>`],
    ],
  },
}

const content = computed(() => {
  const c = CONTENT[locale.value] || CONTENT.en
  return `<h1>${c.title}</h1><p class="updated">${c.updated}</p>` +
    c.sections.map(([h, b]) => `<h2>${h}</h2>${b}`).join('')
})
</script>

<style scoped>
.legal-page { min-height: 100vh; background: #fff; font-family: 'Space Grotesk', 'Noto Sans SC', sans-serif; }
.legal-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 28px; border-bottom: 1px solid #eee; }
.brand { font-weight: 800; letter-spacing: 2px; color: #FF4500; cursor: pointer; }
.legal-body { max-width: 760px; margin: 0 auto; padding: 40px 24px 80px; line-height: 1.8; font-size: 14px; color: #222; }
.legal-body :deep(h1) { font-size: 26px; }
.legal-body :deep(h2) { font-size: 17px; margin-top: 30px; border-left: 3px solid #FF4500; padding-left: 10px; }
.legal-body :deep(p.updated) { color: #999; font-size: 12px; }
</style>
