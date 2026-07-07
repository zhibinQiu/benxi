<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { NIcon } from "naive-ui";
import { CheckmarkCircleOutline } from "@vicons/ionicons5";
import { useAppPreferences } from "../composables/useAppPreferences";
import { messages } from "../locales";

const router = useRouter();
const { locale, isDark } = useAppPreferences();

const BASE = import.meta.env.BASE_URL.replace(/\/+$/, "");

function imgUrl(path) {
  if (!path) return "";
  if (/^https?:\/\//.test(path)) return path;
  return `${BASE}${path}`;
}

const visionEl = ref(null);
const ontologyEl = ref(null);
const skillsEl = ref(null);
const featuresEl = ref(null);
const testimonialsEl = ref(null);
const summaryEl = ref(null);
const footerEl = ref(null);

const dict = computed(() => messages[locale.value] || messages.zh);

const vision = computed(() => dict.value?.login?.showcaseVision || null);
const ontology = computed(() => dict.value?.login?.showcaseOntology || null);
const skills = computed(() => dict.value?.login?.showcaseSkills || null);
const featuresMeta = computed(() => dict.value?.login?.showcaseFeatures || null);
const summary = computed(() => dict.value?.login?.showcaseSummary || null);
const testimonials = computed(() => dict.value?.login?.showcaseTestimonials || null);
const footerData = computed(() => dict.value?.login?.showcaseFooter || null);

function onLegalClick(item) {
  if (item.external) return;
  router.push(item.url);
}

const SUMMARY_COMPARE_KEYS = ["dify", "coze", "fastgpt", "codex", "manus", "chatgpt", "ours"];

const compareKeys = computed(() => {
  const order = summary.value?.compareOrder;
  if (Array.isArray(order) && order.length) return order;
  const cols = summary.value?.columns;
  if (!cols || typeof cols !== "object") return SUMMARY_COMPARE_KEYS;
  const keys = Object.keys(cols).filter((k) => k !== "feature");
  const ours = keys.filter((k) => k === "ours");
  const rest = keys.filter((k) => k !== "ours");
  return [...rest, ...ours];
});

const testimonialsBgStyle = computed(() => {
  const gradient = isDark.value
    ? 'linear-gradient(to bottom, rgba(15,15,22,0.78) 0%, rgba(15,15,22,0.85) 70%, rgba(15,15,22,1) 100%)'
    : 'linear-gradient(to bottom, rgba(255,255,255,0.78) 0%, rgba(255,255,255,0.85) 70%, rgba(255,255,255,1) 100%)';
  return {
    backgroundImage: `${gradient}, url(${imgUrl('/images/bg.jpg')})`,
    backgroundSize: 'cover',
    backgroundPosition: 'center'
  };
});

let revealObserver = null;

function collectSectionEls() {
  return [visionEl.value, ontologyEl.value, skillsEl.value, featuresEl.value, testimonialsEl.value, summaryEl.value, footerEl.value].filter(Boolean);
}

function bindObservers() {
  revealObserver?.disconnect();
  const sections = collectSectionEls();
  if (!sections.length) return;
  revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("login-feature-scroll__section--visible");
        }
      });
    },
    { threshold: 0.06, rootMargin: "0px 0px -5% 0px" }
  );
  sections.forEach((el) => revealObserver.observe(el));
}

onMounted(() => nextTick(bindObservers));
onUnmounted(() => revealObserver?.disconnect());
watch(locale, () => nextTick(bindObservers));
</script>

<template>
  <div class="login-feature-scroll" :style="{ '--bg-url': `url(${imgUrl('/images/bg.jpg')})` }">

    <!-- 产品愿景 -->
    <section
      v-if="vision"
      ref="visionEl"
      data-section="vision"
      class="login-feature-scroll__section"
    >
      <div class="login-feature-scroll__inner login-feature-scroll__inner--wide">
        <div class="login-feature-scroll__split">
          <div class="login-feature-scroll__text">
            <h2 class="login-feature-scroll__title">{{ vision.title }}</h2>
            <p class="login-feature-scroll__body">{{ vision.body }}</p>
          </div>
          <div v-if="vision.image" class="login-feature-scroll__image-wrapper">
            <div class="login-feature-scroll__image-backplate">
              <img :src="imgUrl(vision.image)" alt="" class="login-feature-scroll__img" loading="lazy" />
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 本体论 -->
    <section
      v-if="ontology"
      ref="ontologyEl"
      data-section="ontology"
      class="login-feature-scroll__section"
    >
      <div class="login-feature-scroll__inner login-feature-scroll__inner--wide">
        <div class="login-feature-scroll__split login-feature-scroll__split--reverse">
          <div class="login-feature-scroll__text">
            <h2 class="login-feature-scroll__title">{{ ontology.title }}</h2>
            <p class="login-feature-scroll__body">{{ ontology.body }}</p>
          </div>
          <div v-if="ontology.image" class="login-feature-scroll__image-wrapper">
            <div class="login-feature-scroll__image-backplate">
              <img :src="imgUrl(ontology.image)" alt="" class="login-feature-scroll__img" loading="lazy" />
            </div>
          </div>
      </div>
    </div>
    </section>

    <!-- 多智能体架构 -->
    <section
      v-if="skills"
      ref="skillsEl"
      data-section="skills"
      class="login-feature-scroll__section"
    >
      <div class="login-feature-scroll__inner login-feature-scroll__inner--wide">
        <div class="login-feature-scroll__split">
          <div class="login-feature-scroll__text">
            <h2 class="login-feature-scroll__title">{{ skills.title }}</h2>
            <p class="login-feature-scroll__body">{{ skills.body }}</p>
          </div>
          <div v-if="skills.image" class="login-feature-scroll__image-wrapper">
            <div class="login-feature-scroll__image-backplate">
              <img :src="imgUrl(skills.image)" alt="" class="login-feature-scroll__img" loading="lazy" />
            </div>
          </div>
      </div>
    </div>
    </section>

    <!-- 核心功能 -->
    <section
      v-if="featuresMeta"
      ref="featuresEl"
      data-section="features"
      class="login-feature-scroll__section"
    >
      <div class="login-feature-scroll__inner login-feature-scroll__inner--wide">
        <div class="login-feature-scroll__split login-feature-scroll__split--reverse">
          <div class="login-feature-scroll__text">
            <h2 class="login-feature-scroll__title">{{ featuresMeta.title }}</h2>
            <p v-if="featuresMeta.subtitle" class="login-feature-scroll__body login-feature-scroll__body--subtitle">{{ featuresMeta.subtitle }}</p>
            <div v-if="featuresMeta.items?.length" class="login-feature-scroll__features-grid">
              <div v-for="(item, i) in featuresMeta.items" :key="`fi-${i}`" class="login-feature-scroll__feature-item">
                <h3 class="login-feature-scroll__feature-title">{{ item.title }}</h3>
                <p class="login-feature-scroll__feature-body">{{ item.body }}</p>
              </div>
            </div>
          </div>
          <div v-if="featuresMeta.image" class="login-feature-scroll__image-wrapper">
            <div class="login-feature-scroll__image-backplate">
              <img :src="imgUrl(featuresMeta.image)" alt="" class="login-feature-scroll__img" loading="lazy" />
            </div>
          </div>
        </div>
      </div>
        </section>
    
    <!-- 对比 -->
    <section
      v-if="summary"
      ref="summaryEl"
      data-section="compare"
      class="login-feature-scroll__section login-feature-scroll__section--compare"
    >
      <div class="login-feature-scroll__inner login-feature-scroll__inner--wide">
        <h2 class="login-feature-scroll__title">{{ summary.title }}</h2>

        <div class="login-feature-scroll__compare-wrap">
          <table class="login-feature-scroll__compare-table">
            <thead>
              <tr>
                <th scope="col" class="login-feature-scroll__compare-feature-col">{{ summary.columns?.feature }}</th>
                <th v-for="key in compareKeys" :key="key" scope="col" :class="{ 'login-feature-scroll__compare-ours-col': key === 'ours' }">{{ summary.columns?.[key] }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, ri) in summary.rows" :key="ri">
                <th scope="row" class="login-feature-scroll__compare-feature">{{ row.feature }}</th>
                <td v-for="key in compareKeys" :key="key" :class="{ 'login-feature-scroll__compare-ours-col': key === 'ours' }">
                  <n-icon v-if="row[key]" :size="22" :component="CheckmarkCircleOutline" class="login-feature-scroll__compare-yes" />
                  <span v-else class="login-feature-scroll__compare-no">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <p v-if="summary.closing" class="login-feature-scroll__footnote">{{ summary.closing }}</p>
      </div>
    </section>

    <!-- 用户反馈 -->
    <section
      v-if="testimonials?.items?.length"
      ref="testimonialsEl"
      data-section="testimonials"
      class="login-feature-scroll__section login-feature-scroll__section--testimonials"
      :style="testimonialsBgStyle"
    >
      <div class="login-feature-scroll__inner login-feature-scroll__inner--wide">
        <h2 class="login-feature-scroll__title">{{ testimonials.title }}</h2>
        <div class="login-feature-scroll__testimonials">
          <div v-for="(item, i) in testimonials.items" :key="`t-${i}`" class="login-feature-scroll__testimonial">
            <p class="login-feature-scroll__testimonial-quote">{{ item.quote }}</p>
            <div class="login-feature-scroll__testimonial-author">
              <span>{{ item.author }} · {{ item.role }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 底部链接 -->
    <section
      v-if="footerData?.links?.length"
      ref="footerEl"
      data-section="footer"
      class="login-feature-scroll__section login-feature-scroll__section--footer"
    >
      <div class="login-feature-scroll__footer">
        <div class="login-feature-scroll__footer-links">
          <template v-for="(link, i) in footerData.links" :key="`fl-${i}`">
            <a v-if="link.external" :href="link.url" target="_blank" rel="noopener noreferrer" class="login-feature-scroll__footer-link login-feature-scroll__footer-link--external">{{ link.text }}</a>
            <button v-else type="button" class="login-feature-scroll__footer-link login-feature-scroll__footer-link--btn" @click="router.push(link.url)">{{ link.text }}</button>
          </template>
        </div>
        <div v-if="footerData.legal?.length" class="login-feature-scroll__footer-legal">
          <template v-for="(item, i) in footerData.legal" :key="`fl-legal-${i}`">
            <a v-if="item.external" :href="item.url" target="_blank" rel="noopener noreferrer" class="login-feature-scroll__footer-link login-feature-scroll__footer-link--legal">{{ item.text }}</a>
            <button v-else type="button" class="login-feature-scroll__footer-link login-feature-scroll__footer-link--legal login-feature-scroll__footer-link--btn" @click="router.push(item.url)">{{ item.text }}</button>
          </template>
        </div>
      </div>
    </section>
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
</style>
<style scoped>
.login-feature-scroll {
  width: 100%;
  font-family: "Inter", ui-sans-serif, -apple-system, BlinkMacSystemFont,
    "Segoe UI", "PingFang SC", "Helvetica Neue", "Microsoft YaHei", sans-serif;
}

/* ---------- sections ---------- */
.login-feature-scroll__section {
  position: relative;
  display: flex;
  justify-content: center;
  padding: 140px max(100px, env(safe-area-inset-right, 0px)) 140px max(100px, env(safe-area-inset-left, 0px));
  background: #fff;
}

html[data-theme="dark"] .login-feature-scroll__section {
  background: #0f0f16;
}

.login-feature-scroll__section--compare {
  padding-top: 80px;
  padding-bottom: 100px;
}

.login-feature-scroll__section--footer {
  padding: 0 0 38px;
  background: #fff;
}

html[data-theme="dark"] .login-feature-scroll__section--footer {
  background: #0f0f16;
}

/* ---------- reveal animation ---------- */
.login-feature-scroll__section {
  perspective: 1200px;
}

.login-feature-scroll__inner {
  width: 100%;
  max-width: 1104px;
  margin: 0 auto;
  opacity: 0;
  transform: translateY(40px) rotateX(8deg);
  transform-origin: top center;
  transition: opacity 0.7s cubic-bezier(0.16, 1, 0.3, 1), transform 0.7s cubic-bezier(0.16, 1, 0.3, 1);
}

.login-feature-scroll__inner--wide {
  max-width: 1440px;
}

.login-feature-scroll__section--visible .login-feature-scroll__inner,
.login-feature-scroll__section--visible .login-feature-scroll__footer {
  opacity: 1;
  transform: translateY(0);
}

.login-feature-scroll__title {
  margin: 0 0 12px;
  font-size: clamp(1.2rem, 2.4vw, 1.55rem);
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.03em;
  color: #000;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

html[data-theme="dark"] .login-feature-scroll__title {
  color: #e0e0e8;
}

.login-feature-scroll__body {
  margin: 0;
  font-size: clamp(15px, 1.25vw, 17px);
  line-height: 1.65;
  color: #000;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

html[data-theme="dark"] .login-feature-scroll__body {
  color: #c8c8d0;
}

.login-feature-scroll__body--subtitle {
  margin-bottom: 19px;
  font-weight: 600;
}

/* ---------- split layout ---------- */
.login-feature-scroll__split {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 160px;
  margin-top: 9px;
}

.login-feature-scroll__split .login-feature-scroll__text {
  flex: 0 1 auto;
  width: auto;
  max-width: 30em;
}

.login-feature-scroll__split .login-feature-scroll__image-wrapper {
  flex: 0 1 auto;
  width: auto;
  max-width: 55%;
}

.login-feature-scroll__image-backplate {
  position: relative;
  padding: 16px;
  border-radius: 16px;
  background: #fff;
  background-image: var(--bg-url);
  background-size: cover;
  background-position: center;
  box-shadow: none;
  isolation: isolate;
  overflow: hidden;
}

.login-feature-scroll__image-backplate::before {
  content: "";
  position: absolute;
  inset: 0;
  background: rgba(255,255,255,0.6);
  z-index: 1;
  border-radius: 16px;
}

.login-feature-scroll__split--reverse {
  flex-direction: row-reverse;
}

.login-feature-scroll__text {
  flex: 1 1 50%;
  min-width: 0;
}

.login-feature-scroll__image-wrapper {
  flex: 1 1 50%;
  min-width: 0;
}

html[data-theme="dark"] .login-feature-scroll__image-backplate {
  background-image: var(--bg-url);
  background-size: cover;
  background-position: center;
  box-shadow: none;
}

html[data-theme="dark"] .login-feature-scroll__image-backplate::before {
  background: rgba(15,15,22,0.7);
}

.login-feature-scroll__img {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 14px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  background: #fff;
  position: relative;
  z-index: 2;
}

html[data-theme="dark"] .login-feature-scroll__img {
  border-color: rgba(255, 255, 255, 0.08);
  background: #1a1a24;
}

/* ---------- features grid ---------- */
.login-feature-scroll__features-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 18px;
  margin-top: 14px;
}

.login-feature-scroll__feature-item {
  padding: 0;
}

.login-feature-scroll__feature-title {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 600;
  color: #000;
}

html[data-theme="dark"] .login-feature-scroll__feature-title {
  color: #e0e0e8;
}

.login-feature-scroll__feature-body {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #555;
}

html[data-theme="dark"] .login-feature-scroll__feature-body {
  color: #999;
}

.login-feature-scroll__section[data-section="testimonials"] .login-feature-scroll__title {
  text-align: center;
  font-size: clamp(1.5rem, 3vw, 2rem);
}

.login-feature-scroll__testimonials {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 19px;
}

.login-feature-scroll__testimonial {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 0;
  padding: 20px 22px;
  border-radius: 12px;
  background: #f8f8fa;
  border: 1px solid #e8e8ee;
}

html[data-theme="dark"] .login-feature-scroll__testimonial {
  background: #181820;
  border-color: #2a2a36;
}

.login-feature-scroll__testimonial-quote {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: #000;
  font-style: normal;
}

html[data-theme="dark"] .login-feature-scroll__testimonial-quote {
  color: #d0d0d8;
}

.login-feature-scroll__testimonial-author {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: auto;
  font-size: 13px;
  color: #999;
}

html[data-theme="dark"] .login-feature-scroll__testimonial-author {
  color: #888;
}

/* ---------- compare table ---------- */
.login-feature-scroll__compare-wrap {
  width: 100%;
  margin-top: 19px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  overflow-y: hidden;
}

.login-feature-scroll__compare-table {
  width: 100%;
  min-width: 960px;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 15px;
  line-height: 1.55;
  border-radius: 10px;
  overflow: hidden;
}

.login-feature-scroll__compare-table thead th {
  padding: 10px 12px 12px;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-align: center;
  color: #999;
  border-bottom: 1px solid #e8e8ee;
}

html[data-theme="dark"] .login-feature-scroll__compare-table thead th {
  color: #777;
  border-color: #2a2a36;
}

.login-feature-scroll__compare-feature-col {
  text-align: left !important;
}

.login-feature-scroll__compare-table tbody tr + tr th,
.login-feature-scroll__compare-table tbody tr + tr td {
  border-top: 1px solid #e8e8ee;
}

html[data-theme="dark"] .login-feature-scroll__compare-table tbody tr + tr th,
html[data-theme="dark"] .login-feature-scroll__compare-table tbody tr + tr td {
  border-color: #2a2a36;
}

.login-feature-scroll__compare-table tbody th,
.login-feature-scroll__compare-table tbody td {
  padding: 10px 12px;
  vertical-align: middle;
}

.login-feature-scroll__compare-table tbody td {
  text-align: center;
}

.login-feature-scroll__compare-table tbody tr {
  background: #f8f8fa;
  transition: opacity 0.15s ease;
}

html[data-theme="dark"] .login-feature-scroll__compare-table tbody tr {
  background: #181820;
}

.login-feature-scroll__compare-table tbody tr:hover {
  filter: brightness(0.97);
}

html[data-theme="dark"] .login-feature-scroll__compare-table tbody tr:hover {
  filter: brightness(1.2);
}

.login-feature-scroll__compare-feature {
  font-weight: 600;
  text-align: left;
  color: #111;
  white-space: nowrap;
}

html[data-theme="dark"] .login-feature-scroll__compare-feature {
  color: #e8e8ee;
}

.login-feature-scroll__compare-ours-col {
  background: color-mix(in srgb, var(--platform-accent) 6%, transparent);
}

.login-feature-scroll__compare-table thead .login-feature-scroll__compare-ours-col {
  color: var(--platform-accent);
}

.login-feature-scroll__compare-yes {
  color: var(--platform-accent);
  vertical-align: middle;
}

.login-feature-scroll__compare-no {
  color: #ccc;
  font-size: 17px;
}

html[data-theme="dark"] .login-feature-scroll__compare-no {
  color: #555;
}

.login-feature-scroll__footnote {
  margin: 24px 0 0;
  padding-top: 19px;
  border-top: 1px solid #e8e8ee;
  font-size: 17px;
  line-height: 1.65;
  font-weight: 500;
  color: #111;
}

html[data-theme="dark"] .login-feature-scroll__footnote {
  border-color: #2a2a36;
  color: #e8e8ee;
}

/* ---------- footer ---------- */
.login-feature-scroll__footer {
  width: 100%;
  padding: 48px 26px 19px;
  opacity: 0;
  transform: translateY(40px) rotateX(8deg);
  transform-origin: top center;
  transition: opacity 0.7s cubic-bezier(0.16, 1, 0.3, 1), transform 0.7s cubic-bezier(0.16, 1, 0.3, 1);
}

.login-feature-scroll__footer-links {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px 24px;
  margin-bottom: 19px;
}

.login-feature-scroll__footer-link {
  font-size: 15px;
  font-weight: 500;
  color: #777;
  text-decoration: none;
  transition: color 0.18s ease;
  white-space: nowrap;
}

.login-feature-scroll__footer-link:hover {
  color: var(--platform-accent);
}

.login-feature-scroll__footer-link--external::after {
  content: " ↗";
  font-size: 13px;
}

/* ---------- social links ---------- */
.login-feature-scroll__footer-legal {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px 20px;
  padding-top: 14px;
  border-top: 1px solid #e8e8ee;
}

html[data-theme="dark"] .login-feature-scroll__footer-legal {
  border-color: #2a2a36;
}

.login-feature-scroll__footer-link--legal {
  font-size: 13px;
  color: #bbb;
}

.login-feature-scroll__footer-link--btn {
  appearance: none;
  border: none;
  padding: 0;
  margin: 0;
  background: none;
  font: inherit;
  cursor: pointer;
}

/* ---------- responsive ---------- */
@media (max-width: 1024px) {
  .login-feature-scroll__split {
    gap: 60px;
  }
}

@media (max-width: 900px) {
  .login-feature-scroll__section {
    padding-inline: max(48px, env(safe-area-inset-left, 0px)) max(48px, env(safe-area-inset-right, 0px));
  }

  .login-feature-scroll__split {
    flex-direction: column;
    gap: 40px;
  }
  .login-feature-scroll__split--reverse {
    flex-direction: column;
  }

  .login-feature-scroll__testimonials {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .login-feature-scroll__section {
    padding-inline: max(19px, env(safe-area-inset-left, 0px)) max(19px, env(safe-area-inset-right, 0px));
    padding-block: 64px;
  }

  .login-feature-scroll__section--compare {
    padding-block: 48px 64px;
  }

  .login-feature-scroll__inner {
    max-width: calc(100vw - 38px);
  }

  .login-feature-scroll__compare-table {
    min-width: 720px;
  }

  .login-feature-scroll__compare-feature {
    white-space: normal;
    font-size: 14px;
  }

  .login-feature-scroll__features-grid {
    grid-template-columns: 1fr 1fr;
    gap: 8px 14px;
  }
}

@media (max-width: 480px) {
  .login-feature-scroll__section {
    padding-inline: max(14px, env(safe-area-inset-left, 0px)) max(14px, env(safe-area-inset-right, 0px));
    padding-block: 48px;
  }

  .login-feature-scroll__section--compare {
    padding-block: 36px 48px;
  }

  .login-feature-scroll__split {
    gap: 24px;
  }

  .login-feature-scroll__image-backplate {
    padding: 8px;
    border-radius: 10px;
  }

  .login-feature-scroll__img {
    border-radius: 8px;
  }

  .login-feature-scroll__features-grid {
    grid-template-columns: 1fr;
    gap: 6px;
  }

  .login-feature-scroll__testimonial {
    padding: 14px 16px;
  }

  .login-feature-scroll__testimonial-quote {
    font-size: 13px;
  }

  .login-feature-scroll__footer {
    padding: 28px 14px 14px;
  }

  .login-feature-scroll__footer-links {
    gap: 6px 14px;
  }

  .login-feature-scroll__footer-link {
    font-size: 13px;
  }

  .login-feature-scroll__compare-table thead th {
    padding: 8px 6px;
    font-size: 12px;
  }

  .login-feature-scroll__compare-table tbody th,
  .login-feature-scroll__compare-table tbody td {
    padding: 7px 6px;
    font-size: 13px;
  }
}

@media (max-width: 400px) {
  .login-feature-scroll__section {
    padding-block: 36px;
  }

  .login-feature-scroll__title {
    font-size: 1.1rem;
  }

  .login-feature-scroll__body {
    font-size: 14px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .login-feature-scroll__inner,
  .login-feature-scroll__footer {
    opacity: 1 !important;
    transform: none !important;
    transition: none !important;
  }
}
</style>
