<template>
  <div class="landing">
    <!-- Nav -->
    <header class="nav">
      <div class="nav-brand" @click="$router.push('/')" style="cursor:pointer"><svg width="20" height="20" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg" style="display:block;flex-shrink:0;margin-right:8px"><rect width="32" height="32" rx="7" fill="#FF4500"/><circle cx="16" cy="16" r="10" stroke="white" stroke-width="2" fill="none" opacity="0.35"/><circle cx="16" cy="16" r="6" stroke="white" stroke-width="2" fill="none" opacity="0.65"/><circle cx="16" cy="16" r="3" fill="white"/><circle cx="23" cy="9" r="3" fill="white"/></svg>YANCEVA</div>
      <nav class="nav-links">
        <a href="#how">{{ $t('landing.navHow') }}</a>
        <a href="#pricing">{{ $t('landing.navPricing') }}</a>
        <a href="#faq">FAQ</a>
      </nav>
      <div class="nav-actions">
        <LanguageSwitcher />
        <button class="cta-btn small" @click="$router.push('/orders')">{{ $t('landing.ctaOrder') }}</button>
      </div>
    </header>

    <!-- Hero -->
    <section class="hero">
      <div class="hero-badge">{{ $t('landing.heroBadge') }}</div>
      <h1 class="hero-title">{{ $t('landing.heroTitle') }}</h1>
      <p class="hero-sub">{{ $t('landing.heroSub') }}</p>
      <div class="hero-cta">
        <button class="cta-btn" @click="$router.push('/orders')">{{ $t('landing.ctaPrimary') }}</button>
        <a class="ghost-btn" href="#how">{{ $t('landing.ctaSecondary') }}</a>
      </div>
      <div class="hero-stats">
        <div class="stat"><b>{{ $t('landing.stat1Value') }}</b><span>{{ $t('landing.stat1Label') }}</span></div>
        <div class="stat"><b>{{ $t('landing.stat2Value') }}</b><span>{{ $t('landing.stat2Label') }}</span></div>
        <div class="stat"><b>{{ $t('landing.stat3Value') }}</b><span>{{ $t('landing.stat3Label') }}</span></div>
      </div>
    </section>

    <!-- How it works -->
    <section id="how" class="how">
      <h2>{{ $t('landing.howTitle') }}</h2>
      <p class="how-sub">{{ $t('landing.howSub') }}</p>
      <div class="steps">
        <div class="step" v-for="i in 4" :key="i">
          <div class="step-num">0{{ i }}</div>
          <h3>{{ $t(`landing.step${i}Title`) }}</h3>
          <p>{{ $t(`landing.step${i}Desc`) }}</p>
        </div>
      </div>
    </section>

    <!-- Value -->
    <section class="value">
      <h2>{{ $t('landing.valueTitle') }}</h2>
      <div class="value-grid">
        <div class="value-card" v-for="i in 4" :key="i">
          <h3>{{ $t(`landing.value${i}Title`) }}</h3>
          <p>{{ $t(`landing.value${i}Desc`) }}</p>
        </div>
      </div>
    </section>

    <!-- Pricing -->
    <section id="pricing" class="pricing">
      <h2>{{ $t('landing.pricingTitle') }}</h2>
      <div class="pricing-cards">
        <button
          v-for="p in products" :key="p.product_id"
          class="price-card"
          @click="$router.push('/orders')"
        >
          <div class="pc-name">{{ p.name }}</div>
          <div class="pc-price">
            ${{ (p.price_cents / 100).toFixed(0) }}<span>/{{ $t('order.perRun') }}</span>
            <span class="cny-ref" v-if="locale === 'zh'">≈ ¥{{ Math.round(p.price_cents / 100 * 7.25) }}</span>
          </div>
          <div class="pc-tagline">{{ p.tagline }}</div>
          <div class="pc-sla">{{ $t('order.slaLabel') }} ~{{ p.sla_minutes }}min</div>
        </button>
      </div>
    </section>

    <!-- FAQ (SEO: FAQPage) -->
    <section id="faq" class="faq">
      <h2>FAQ</h2>
      <details v-for="(q, i) in faqs" :key="i" class="faq-item">
        <summary>{{ q.q }}</summary>
        <p>{{ q.a }}</p>
      </details>
    </section>

    <!-- Sample insights (真实推演发现) -->
    <section class="insights">
      <h2>{{ $t('landing.insightsTitle') }}</h2>
      <p class="insights-sub">{{ $t('landing.insightsSub') }}</p>
      <div class="insight-cards">
        <div class="insight-card" v-for="i in 3" :key="i">
          <span class="insight-tag">{{ $t(`landing.sample${i}Tag`) }}</span>
          <p class="insight-quote">{{ $t(`landing.sample${i}Quote`) }}</p>
          <div class="insight-metric">{{ $t(`landing.sample${i}Metric`) }}</div>
        </div>
      </div>
    </section>

    <!-- Testimonials -->
    <section class="testimonials">
      <h2>{{ $t('landing.testimonialsTitle') }}</h2>
      <div class="testimonial-grid">
        <div class="testimonial-card" v-for="i in 3" :key="i">
          <div class="t-avatar">{{ ['A', 'B', 'C'][i-1] }}</div>
          <p class="t-quote">"{{ $t(`landing.t${i}Quote`) }}"</p>
          <div class="t-meta">
            <span class="t-name">{{ $t(`landing.t${i}Name`) }}</span>
            <span class="t-role">{{ $t(`landing.t${i}Role`) }}</span>
          </div>
        </div>
      </div>
      <p class="testimonial-note">{{ $t('landing.testimonialsNote') }}</p>
    </section>

    <!-- Final CTA -->
    <section class="final-cta">
      <h2>{{ $t('landing.finalTitle') }}</h2>
      <button class="cta-btn" @click="$router.push('/orders')">{{ $t('landing.ctaPrimary') }}</button>
    </section>

    <!-- Footer -->
    <footer class="footer">
      <div class="footer-links">
        <router-link to="/privacy">{{ $t('legal.privacy') }}</router-link>
        <router-link to="/terms">{{ $t('legal.terms') }}</router-link>
        <a href="mailto:support@example.com">{{ $t('legal.contact') }}</a>
      </div>
      <div class="footer-note">© 2026 Yanceva Rehearsal Platform · {{ $t('landing.footerDisclaimer') }}</div>
    </footer>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import LanguageSwitcher from '../components/LanguageSwitcher.vue'
import { listProducts } from '../api/orders'

const { t, locale } = useI18n()

const products = ref([])
async function loadLanding() {
  document.title = t('landing.docTitle')
  document.querySelector('meta[name="description"]')
    ?.setAttribute('content', t('landing.docDesc'))
  const res = await listProducts()
  if (res.success && res.data) products.value = res.data
}

watch(locale, () => { loadLanding() })

onMounted(() => { loadLanding() })

const faqs = computed(() => [
  { q: t('landing.faq1Q'), a: t('landing.faq1A') },
  { q: t('landing.faq2Q'), a: t('landing.faq2A') },
  { q: t('landing.faq3Q'), a: t('landing.faq3A') },
  { q: t('landing.faq4Q'), a: t('landing.faq4A') },
  { q: t('landing.faq5Q'), a: t('landing.faq5A') },
])
</script>

<style scoped>
.landing { font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif; color: #111; background: #fff; }
.nav {
  display: flex; align-items: center; gap: 24px;
  padding: 16px 5vw; border-bottom: 1px solid #eee; position: sticky; top: 0;
  background: rgba(255,255,255,.95); backdrop-filter: blur(6px); z-index: 100;
}
.nav-brand { font-weight: 800; letter-spacing: 2px; color: #FF4500; display: flex; align-items: center; cursor: pointer; }
.nav-links { flex: 1; display: flex; gap: 22px; font-size: 14px; }
.nav-links a { color: #333; text-decoration: none; }
.nav-links a:hover { color: #FF4500; }
.nav-actions { display: flex; align-items: center; gap: 12px; }

.hero { text-align: center; padding: 80px 5vw 60px; background: linear-gradient(180deg, #fff8f4 0%, #fff 100%); }
.hero-badge { display: inline-block; font-size: 12px; letter-spacing: 1px; color: #FF4500; border: 1px solid #FFD2BF; border-radius: 20px; padding: 4px 14px; margin-bottom: 18px; }
.hero-title { font-size: clamp(28px, 4.5vw, 46px); line-height: 1.2; margin: 0 auto 16px; max-width: 820px; }
.hero-sub { font-size: clamp(14px, 1.6vw, 17px); color: #555; max-width: 640px; margin: 0 auto 28px; }
.hero-cta { display: flex; gap: 14px; justify-content: center; }
.cta-btn {
  background: #FF4500; color: #fff; border: none; border-radius: 10px;
  padding: 14px 32px; font-size: 15px; font-weight: 700; cursor: pointer;
}
.cta-btn.small { padding: 8px 18px; font-size: 13px; }
.cta-btn:hover { background: #e03d00; }
.ghost-btn {
  border: 1px solid #ddd; background: #fff; color: #333; border-radius: 10px;
  padding: 14px 28px; font-size: 15px; cursor: pointer; text-decoration: none; display: inline-block;
}
.hero-stats { display: flex; gap: 40px; justify-content: center; margin-top: 44px; flex-wrap: wrap; }
.stat b { display: block; font-size: 22px; color: #FF4500; }
.stat span { font-size: 12px; color: #888; }

section h2 { text-align: center; font-size: clamp(22px, 3vw, 30px); margin: 0 0 8px; }
.how { padding: 70px 5vw; background: #fafafa; }
.how-sub { text-align: center; color: #666; margin-bottom: 36px; font-size: 14px; }
.steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 18px; max-width: 1060px; margin: 0 auto; }
.step { background: #fff; border: 1px solid #eee; border-radius: 12px; padding: 20px; }
.step-num { font-family: 'JetBrains Mono', monospace; color: #FF4500; font-weight: 800; margin-bottom: 8px; }
.step h3 { font-size: 15px; margin: 0 0 6px; }
.step p { font-size: 13px; color: #666; line-height: 1.6; margin: 0; }

.value { padding: 70px 5vw; }
.value-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 18px; max-width: 1060px; margin: 36px auto 0; }
.value-card { border-left: 3px solid #FF4500; padding: 6px 0 6px 18px; }
.value-card h3 { font-size: 16px; margin: 0 0 8px; }
.value-card p { font-size: 13px; color: #666; line-height: 1.7; margin: 0; }

.pricing { padding: 70px 5vw; background: #fafafa; }
.pricing-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 18px; max-width: 1060px; margin: 36px auto 0; }
.price-card {
  text-align: left; background: #fff; border: 1px solid #eee; border-radius: 14px;
  padding: 24px; cursor: pointer; display: flex; flex-direction: column; gap: 10px;
  transition: transform .15s, border-color .15s; font-family: inherit;
}
.price-card:hover {
  transform: translateY(-4px); border-color: #FF4500;
  box-shadow: 0 6px 24px rgba(255, 69, 0, 0.12);
}
.pc-name { font-weight: 700; font-size: 15px; }
.pc-price { font-size: 30px; font-weight: 800; color: #FF4500; }
.pc-price span { font-size: 13px; color: #999; font-weight: 400; }
.cny-ref { font-size: 13px; color: #999; margin-left: 6px; }
.pc-tagline { font-size: 12px; color: #666; line-height: 1.6; flex: 1; }
.pc-sla { font-size: 11px; color: #999; }
.price-card.more { border-style: dashed; color: #999; align-items: center; justify-content: center; text-align: center; }
.price-card.more .pc-name { color: #666; }

.faq { padding: 70px 5vw; max-width: 780px; margin: 0 auto; }
.faq-item { border: 1px solid #eee; border-radius: 10px; padding: 14px 20px; margin-bottom: 10px; background: #fff; }
.faq-item summary { font-weight: 600; font-size: 14px; cursor: pointer; }
.faq-item p { font-size: 13px; color: #555; line-height: 1.7; }

.final-cta { text-align: center; padding: 80px 5vw; background: #141414; color: #fff; }
.final-cta h2 { color: #fff; margin-bottom: 24px; }

.footer { padding: 32px 5vw; border-top: 1px solid #eee; text-align: center; }
.footer-links { display: flex; gap: 24px; justify-content: center; font-size: 13px; margin-bottom: 10px; }
.footer-links a { color: #666; }
.footer-note { color: #aaa; font-size: 12px; }

/* Sample insights */
.insights { padding: 70px 5vw; background: #fafafa; }
.insights-sub { text-align: center; color: #666; font-size: 14px; margin-bottom: 36px; }
.insight-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; max-width: 1060px; margin: 0 auto; }
.insight-card { background: #fff; border: 1px solid #eee; border-radius: 14px; padding: 22px; display: flex; flex-direction: column; gap: 12px; }
.insight-tag { display: inline-block; font-size: 11px; letter-spacing: 1px; color: #FF4500; border: 1px solid #FFD2BF; border-radius: 16px; padding: 3px 12px; width: fit-content; font-weight: 600; }
.insight-quote { font-size: 14px; color: #333; line-height: 1.7; flex: 1; margin: 0; }
.insight-metric { font-size: 12px; color: #999; font-family: 'JetBrains Mono', monospace; border-top: 1px solid #f0f0f0; padding-top: 10px; }

/* Testimonials */
.testimonials { padding: 70px 5vw; }
.testimonial-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 18px; max-width: 1060px; margin: 36px auto 0; }
.testimonial-card { background: #fff; border: 1px solid #eee; border-radius: 14px; padding: 22px; }
.t-avatar { width: 40px; height: 40px; border-radius: 50%; background: #FF4500; color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 16px; margin-bottom: 12px; }
.t-quote { font-size: 13px; color: #444; line-height: 1.7; margin: 0 0 14px; font-style: italic; }
.t-meta { display: flex; flex-direction: column; gap: 2px; }
.t-name { font-weight: 700; font-size: 13px; color: #111; }
.t-role { font-size: 11px; color: #999; }
.testimonial-note { text-align: center; color: #aaa; font-size: 11px; margin-top: 16px; }

</style>
