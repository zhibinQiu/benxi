<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { NIcon } from "naive-ui";
import { CheckmarkCircleOutline } from "@vicons/ionicons5";
import { useAppPreferences } from "../composables/useAppPreferences";
import { messages } from "../locales";
import { openExternal } from "../utils/openExternal";
import { getReportShareUrl } from "../api/finance";
import { fetchPromoStats } from "../api/system";
import { prefersReducedMotion } from "../utils/mediaQuery";

const router = useRouter();
const { locale, isDark } = useAppPreferences();

const BASE = import.meta.env.BASE_URL.replace(/\/+$/, "");

const DEFAULT_PROMO_STATS = {
  documents: 0,
  agents: 7,
  skills: 16,
  tools: 72,
  notes: 0,
  reports: 1960,
  features: 20,
  features_plus: true,
  roundtable_share_token: "",
};

const promoStats = ref({ ...DEFAULT_PROMO_STATS });
const displayStats = ref({
  documents: 0,
  agents: 0,
  skills: 0,
  tools: 0,
  notes: 0,
  reports: 0,
  features: 0,
});
const statsPlayed = ref({
  vision: false,
  skills: false,
  "knowledge-search": false,
  notes: false,
  features: false,
});
const countRafs = new Set();

function formatStat(n) {
  const num = Math.max(0, Math.round(Number(n) || 0));
  return num.toLocaleString("zh-CN");
}

function animateStat(key, target, duration = 1100) {
  const to = Math.max(0, Math.round(Number(target) || 0));
  if (prefersReducedMotion()) {
    displayStats.value = { ...displayStats.value, [key]: to };
    return;
  }
  const from = 0;
  const start = performance.now();
  const tick = (now) => {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - (1 - t) ** 3;
    displayStats.value = {
      ...displayStats.value,
      [key]: Math.round(from + (to - from) * eased),
    };
    if (t < 1) {
      const id = requestAnimationFrame(tick);
      countRafs.add(id);
    }
  };
  const id = requestAnimationFrame(tick);
  countRafs.add(id);
}

function playSectionStats(section) {
  if (!section || statsPlayed.value[section]) return;
  statsPlayed.value = { ...statsPlayed.value, [section]: true };
  const s = promoStats.value;
  if (section === "vision") animateStat("documents", s.documents);
  if (section === "skills") {
    animateStat("agents", s.agents);
    animateStat("skills", s.skills, 1200);
    animateStat("tools", s.tools, 1300);
  }
  if (section === "knowledge-search") animateStat("reports", s.reports, 1400);
  if (section === "notes") animateStat("notes", s.notes, 1200);
  if (section === "features") animateStat("features", s.features);
}

async function loadPromoStats() {
  try {
    const data = await fetchPromoStats();
    if (!data || typeof data !== "object") return;
    promoStats.value = {
      documents: Number(data.documents) || 0,
      agents: Number(data.agents) || DEFAULT_PROMO_STATS.agents,
      skills: Number(data.skills) || DEFAULT_PROMO_STATS.skills,
      tools: Number(data.tools) || DEFAULT_PROMO_STATS.tools,
      notes: Number(data.notes) || 0,
      reports: Number(data.reports) || DEFAULT_PROMO_STATS.reports,
      features: Number(data.features) || DEFAULT_PROMO_STATS.features,
      features_plus: data.features_plus !== false,
      roundtable_share_token: String(data.roundtable_share_token || "").trim(),
    };
    // 若区块已播过动效，用真实值校正终态
    const d = displayStats.value;
    const p = promoStats.value;
    const played = statsPlayed.value;
    displayStats.value = {
      documents: played.vision ? p.documents : d.documents,
      agents: played.skills ? p.agents : d.agents,
      skills: played.skills ? p.skills : d.skills,
      tools: played.skills ? p.tools : d.tools,
      notes: played.notes ? p.notes : d.notes,
      reports: played["knowledge-search"] ? p.reports : d.reports,
      features: played.features ? p.features : d.features,
    };
  } catch {
    /* 保持默认值，宣传页不因统计失败阻塞 */
  }
}

function imgUrl(path) {
  if (!path) return "";
  if (/^https?:\/\//.test(path)) return path;
  return `${BASE}${path}`;
}

/** B 站官方嵌入地址（支持 //player… 或完整 https URL） */
function bilibiliEmbedSrc(raw) {
  const value = String(raw || "").trim();
  if (!value) return "";
  if (value.startsWith("//")) return `https:${value}`;
  if (/player\.bilibili\.com/i.test(value)) return value;
  return "";
}

function isLocalVideoPath(raw) {
  const value = String(raw || "").trim();
  if (!value) return false;
  if (/player\.bilibili\.com/i.test(value)) return false;
  return /\.(mp4|webm|ogg)(\?|#|$)/i.test(value) || value.startsWith("/videos/");
}

/** 本地 mp4 优先；否则回退 B 站嵌入；再否则静态图 */
function resolveShowcaseMedia(section) {
  if (!section) return null;
  const video = String(section.video || "").trim();
  const embed = String(section.videoEmbed || "").trim();
  const posterPath = String(section.poster || section.image || "").trim();
  const poster = posterPath ? imgUrl(posterPath) : "";
  const title = section.title || "";

  if (isLocalVideoPath(video)) {
    return { kind: "file", src: imgUrl(video), poster, title };
  }

  const embedSrc = bilibiliEmbedSrc(embed || video);
  if (embedSrc) {
    return { kind: "embed", src: embedSrc, poster, title };
  }

  if (section.image) {
    return { kind: "image", src: imgUrl(section.image), poster: "", title };
  }
  return null;
}

const visionEl = ref(null);
const skillsEl = ref(null);
const knowledgeSearchEl = ref(null);
const notesEl = ref(null);
const featuresEl = ref(null);
const testimonialsEl = ref(null);
const acknowledgmentsEl = ref(null);
const summaryEl = ref(null);
const footerEl = ref(null);

const dict = computed(() => messages[locale.value] || messages.zh);

const vision = computed(() => dict.value?.login?.showcaseVision || null);
const skills = computed(() => dict.value?.login?.showcaseSkills || null);
const knowledgeSearch = computed(() => dict.value?.login?.showcaseKnowledgeSearch || null);
const notes = computed(() => dict.value?.login?.showcaseNotes || null);
const featuresMeta = computed(() => dict.value?.login?.showcaseFeatures || null);
const summary = computed(() => dict.value?.login?.showcaseSummary || null);
const testimonials = computed(() => dict.value?.login?.showcaseTestimonials || null);
const acknowledgments = computed(() => dict.value?.login?.showcaseAcknowledgments || null);
const footerData = computed(() => dict.value?.login?.showcaseFooter || null);
const statLabels = computed(() => dict.value?.login?.showcaseStatLabels || {});

/** 点击后才挂载播放器，避免首屏拉大视频 */
const mediaActivated = ref({ skills: false, knowledgeSearch: false, notes: false });
/** 本地 mp4 404 时回退到 videoEmbed */
const localVideoFailed = ref({ skills: false, knowledgeSearch: false, notes: false });

function resolveMediaWithFallback(section, key) {
  const media = resolveShowcaseMedia(section);
  if (media?.kind === "file" && localVideoFailed.value[key]) {
    const embedSrc = bilibiliEmbedSrc(section?.videoEmbed);
    if (embedSrc) return { kind: "embed", src: embedSrc, poster: media.poster, title: media.title };
    if (section?.image) return { kind: "image", src: imgUrl(section.image), poster: "", title: media.title };
  }
  return media;
}

const skillsMedia = computed(() => resolveMediaWithFallback(skills.value, "skills"));
const knowledgeSearchMedia = computed(() => resolveMediaWithFallback(knowledgeSearch.value, "knowledgeSearch"));
const notesMedia = computed(() => resolveMediaWithFallback(notes.value, "notes"));

function activateMedia(key) {
  if (!Object.prototype.hasOwnProperty.call(mediaActivated.value, key)) return;
  mediaActivated.value = { ...mediaActivated.value, [key]: true };
}

function onLocalVideoError(key) {
  if (!Object.prototype.hasOwnProperty.call(localVideoFailed.value, key)) return;
  localVideoFailed.value = { ...localVideoFailed.value, [key]: true };
}

// 为致谢卡片生成随机翻转延迟（每次数据变化重新生成）
const ackFlipDelays = computed(() => {
  const items = acknowledgments.value?.items;
  if (!items?.length) return [];
  return items.map(() => `${(Math.random() * 0.7 + 0.1).toFixed(2)}s`);
});

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
  return [
    visionEl.value,
    skillsEl.value,
    knowledgeSearchEl.value,
    notesEl.value,
    featuresEl.value,
    testimonialsEl.value,
    acknowledgmentsEl.value,
    summaryEl.value,
    footerEl.value,
  ].filter(Boolean);
}

function resolveVisionReportUrl() {
  const configured = String(vision.value?.reportUrl || "").trim();
  if (configured) return configured;
  const token = String(promoStats.value.roundtable_share_token || "").trim();
  return token ? getReportShareUrl(token) : "";
}

function openVisionReport() {
  const url = resolveVisionReportUrl();
  if (!url) return;
  openExternal(url);
}

function openReportDemo() {
  const url = String(knowledgeSearch.value?.reportUrl || "").trim();
  if (!url) return;
  openExternal(url);
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
          playSectionStats(entry.target.getAttribute("data-section"));
        }
      });
    },
    { threshold: 0.06, rootMargin: "0px 0px -5% 0px" }
  );
  sections.forEach((el) => revealObserver.observe(el));
}

onMounted(() => {
  loadPromoStats();
  nextTick(bindObservers);
});
onUnmounted(() => {
  revealObserver?.disconnect();
  countRafs.forEach((id) => cancelAnimationFrame(id));
  countRafs.clear();
});
watch(locale, () => {
  mediaActivated.value = { skills: false, knowledgeSearch: false, notes: false };
  localVideoFailed.value = { skills: false, knowledgeSearch: false, notes: false };
  nextTick(bindObservers);
});
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
            <p class="login-feature-scroll__stat">
              {{ statLabels.documentsPrefix || "平台已接入知识库文档" }}
              <span class="login-feature-scroll__stat-num">{{ formatStat(displayStats.documents) }}</span>
              {{ statLabels.unit || "个" }}
            </p>
            <h2 class="login-feature-scroll__title">{{ vision.title }}</h2>
            <p class="login-feature-scroll__body">{{ vision.body }}</p>
            <button
              type="button"
              class="login-feature-scroll__enterprise-link"
              @click="openVisionReport"
            >
              {{ vision.reportCta || "平台生成的真实上市公司分析圆桌报告 →" }}
            </button>
          </div>
          <div v-if="vision.image" class="login-feature-scroll__image-wrapper">
            <div class="login-feature-scroll__image-backplate">
              <div class="login-feature-scroll__media">
                <img :src="imgUrl(vision.image)" alt="" class="login-feature-scroll__img" loading="lazy" />
              </div>
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
            <p class="login-feature-scroll__stat login-feature-scroll__stat--multi">
              <span>
                {{ statLabels.agentsPrefix || "平台已接入智能体" }}
                <span class="login-feature-scroll__stat-num">{{ formatStat(displayStats.agents) }}</span>
                {{ statLabels.unit || "个" }}
              </span>
              <span class="login-feature-scroll__stat-sep" aria-hidden="true">·</span>
              <span>
                {{ statLabels.skillsLabel || "技能" }}
                <span class="login-feature-scroll__stat-num">{{ formatStat(displayStats.skills) }}</span>
                {{ statLabels.unit || "个" }}
              </span>
              <span class="login-feature-scroll__stat-sep" aria-hidden="true">·</span>
              <span>
                {{ statLabels.toolsLabel || "工具" }}
                <span class="login-feature-scroll__stat-num">{{ formatStat(displayStats.tools) }}</span>
                {{ statLabels.unit || "个" }}
              </span>
            </p>
            <h2 class="login-feature-scroll__title">{{ skills.title }}</h2>
            <p class="login-feature-scroll__body">{{ skills.body }}</p>
            <button
              type="button"
              class="login-feature-scroll__enterprise-link"
              @click="router.push('/agentkit-philosophy')"
            >
              了解更多关于 AgentKit 的设计哲学 →
            </button>
          </div>
          <div v-if="skillsMedia" class="login-feature-scroll__image-wrapper">
            <div class="login-feature-scroll__image-backplate">
              <div
                v-if="skillsMedia.kind === 'file' || skillsMedia.kind === 'embed'"
                class="login-feature-scroll__video"
              >
                <button
                  v-if="!mediaActivated.skills"
                  type="button"
                  class="login-feature-scroll__video-poster"
                  :aria-label="`播放：${skillsMedia.title || '演示视频'}`"
                  @click="activateMedia('skills')"
                >
                  <img
                    v-if="skillsMedia.poster"
                    :src="skillsMedia.poster"
                    alt=""
                    class="login-feature-scroll__video-poster-img"
                    loading="lazy"
                  />
                  <span class="login-feature-scroll__video-play" aria-hidden="true" />
                </button>
                <video
                  v-else-if="skillsMedia.kind === 'file'"
                  :src="skillsMedia.src"
                  :poster="skillsMedia.poster || undefined"
                  :aria-label="skillsMedia.title"
                  controls
                  playsinline
                  autoplay
                  preload="none"
                  @error="onLocalVideoError('skills')"
                />
                <iframe
                  v-else
                  :src="skillsMedia.src"
                  :title="skillsMedia.title || 'AgentKit demo'"
                  scrolling="no"
                  border="0"
                  frameborder="no"
                  framespacing="0"
                  allowfullscreen="true"
                />
              </div>
              <div v-else class="login-feature-scroll__media">
                <img
                  :src="skillsMedia.src"
                  alt=""
                  class="login-feature-scroll__img"
                  loading="lazy"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 企业级知识检索与报告生成 -->
    <section
      v-if="knowledgeSearch"
      ref="knowledgeSearchEl"
      data-section="knowledge-search"
      class="login-feature-scroll__section"
    >
      <div class="login-feature-scroll__inner login-feature-scroll__inner--wide">
        <div class="login-feature-scroll__split">
          <div class="login-feature-scroll__text">
            <p class="login-feature-scroll__stat">
              {{ statLabels.reportsPrefix || "平台累计共生成报告" }}
              <span class="login-feature-scroll__stat-num">{{ formatStat(displayStats.reports) }}</span>
              {{ statLabels.unit || "个" }}
            </p>
            <h2 class="login-feature-scroll__title">{{ knowledgeSearch.title }}</h2>
            <p class="login-feature-scroll__body">{{ knowledgeSearch.body }}</p>
            <div class="login-feature-scroll__cta-row">
              <button
                v-if="knowledgeSearch.reportUrl"
                type="button"
                class="login-feature-scroll__enterprise-link login-feature-scroll__enterprise-link--primary"
                @click="openReportDemo"
              >
                {{ knowledgeSearch.reportCta || "查看真实公司分析报告 →" }}
              </button>
              <button
                type="button"
                class="login-feature-scroll__enterprise-link"
                @click="router.push('/enterprise/knowledge')"
              >
                了解更多企业版功能 →
              </button>
            </div>
          </div>
          <div v-if="knowledgeSearchMedia" class="login-feature-scroll__image-wrapper">
            <div class="login-feature-scroll__image-backplate">
              <div
                v-if="knowledgeSearchMedia.kind === 'file' || knowledgeSearchMedia.kind === 'embed'"
                class="login-feature-scroll__video"
              >
                <button
                  v-if="!mediaActivated.knowledgeSearch"
                  type="button"
                  class="login-feature-scroll__video-poster"
                  :aria-label="`播放：${knowledgeSearchMedia.title || '演示视频'}`"
                  @click="activateMedia('knowledgeSearch')"
                >
                  <img
                    v-if="knowledgeSearchMedia.poster"
                    :src="knowledgeSearchMedia.poster"
                    alt=""
                    class="login-feature-scroll__video-poster-img"
                    loading="lazy"
                  />
                  <span class="login-feature-scroll__video-play" aria-hidden="true" />
                </button>
                <video
                  v-else-if="knowledgeSearchMedia.kind === 'file'"
                  :src="knowledgeSearchMedia.src"
                  :poster="knowledgeSearchMedia.poster || undefined"
                  :aria-label="knowledgeSearchMedia.title"
                  controls
                  playsinline
                  autoplay
                  preload="none"
                  @error="onLocalVideoError('knowledgeSearch')"
                />
                <iframe
                  v-else
                  :src="knowledgeSearchMedia.src"
                  :title="knowledgeSearchMedia.title || 'Knowledge search demo'"
                  scrolling="no"
                  border="0"
                  frameborder="no"
                  framespacing="0"
                  allowfullscreen="true"
                />
              </div>
              <div v-else class="login-feature-scroll__media">
                <img
                  :src="knowledgeSearchMedia.src"
                  alt=""
                  class="login-feature-scroll__img"
                  loading="lazy"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 工作笔记 -->
    <section
      v-if="notes"
      ref="notesEl"
      data-section="notes"
      class="login-feature-scroll__section"
    >
      <div class="login-feature-scroll__inner login-feature-scroll__inner--wide">
        <div class="login-feature-scroll__split">
          <div class="login-feature-scroll__text">
            <p class="login-feature-scroll__stat">
              {{ statLabels.notesPrefix || "平台已保存工作笔记" }}
              <span class="login-feature-scroll__stat-num">{{ formatStat(displayStats.notes) }}</span>
              {{ statLabels.notesUnit ?? "篇" }}
            </p>
            <h2 class="login-feature-scroll__title">{{ notes.title }}</h2>
            <p class="login-feature-scroll__body">{{ notes.body }}</p>
          </div>
          <div v-if="notesMedia" class="login-feature-scroll__image-wrapper">
            <div class="login-feature-scroll__image-backplate">
              <div
                v-if="notesMedia.kind === 'file' || notesMedia.kind === 'embed'"
                class="login-feature-scroll__video"
              >
                <button
                  v-if="!mediaActivated.notes"
                  type="button"
                  class="login-feature-scroll__video-poster"
                  :aria-label="`播放：${notesMedia.title || '演示视频'}`"
                  @click="activateMedia('notes')"
                >
                  <img
                    v-if="notesMedia.poster"
                    :src="notesMedia.poster"
                    alt=""
                    class="login-feature-scroll__video-poster-img"
                    loading="lazy"
                  />
                  <span class="login-feature-scroll__video-play" aria-hidden="true" />
                </button>
                <video
                  v-else-if="notesMedia.kind === 'file'"
                  :src="notesMedia.src"
                  :poster="notesMedia.poster || undefined"
                  :aria-label="notesMedia.title"
                  controls
                  playsinline
                  autoplay
                  preload="none"
                  @error="onLocalVideoError('notes')"
                />
                <iframe
                  v-else
                  :src="notesMedia.src"
                  :title="notesMedia.title || 'Notes system demo'"
                  scrolling="no"
                  border="0"
                  frameborder="no"
                  framespacing="0"
                  allowfullscreen="true"
                />
              </div>
              <div v-else class="login-feature-scroll__media">
                <img
                  :src="notesMedia.src"
                  alt=""
                  class="login-feature-scroll__img"
                  loading="lazy"
                />
              </div>
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
        <div class="login-feature-scroll__split">
          <div class="login-feature-scroll__text">
            <p class="login-feature-scroll__stat">
              {{ statLabels.featuresPrefix || "平台已实现功能" }}
              <span class="login-feature-scroll__stat-num">{{ formatStat(displayStats.features) }}</span>
              <span v-if="promoStats.features_plus">{{ statLabels.featuresSuffix || "+" }}</span>
            </p>
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
              <div class="login-feature-scroll__media">
                <img :src="imgUrl(featuresMeta.image)" alt="" class="login-feature-scroll__img" loading="lazy" />
              </div>
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

    <!-- 致谢 -->
    <section
      v-if="acknowledgments?.items?.length"
      ref="acknowledgmentsEl"
      data-section="acknowledgments"
      class="login-feature-scroll__section login-feature-scroll__section--acknowledgments"
    >
      <div class="login-feature-scroll__inner login-feature-scroll__inner--wide">
        <h2 class="login-feature-scroll__title login-feature-scroll__acknowledgments-title">{{ acknowledgments.title }}</h2>
        <p class="login-feature-scroll__acknowledgments-subtitle">{{ acknowledgments.subtitle }}</p>
        <div class="login-feature-scroll__acknowledgments-grid">
          <a
            v-for="(item, i) in acknowledgments.items"
            :key="`ack-${i}`"
            :href="item.url"
            target="_blank"
            rel="noopener noreferrer"
            class="login-feature-scroll__acknowledgment-card"
            :style="{ animationDelay: ackFlipDelays[i] }"
          >
            <span class="login-feature-scroll__acknowledgment-name">{{ item.name }}</span>
            <span class="login-feature-scroll__acknowledgment-desc">{{ item.description }}</span>
          </a>
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
  padding: 96px max(80px, env(safe-area-inset-right, 0px)) 96px max(80px, env(safe-area-inset-left, 0px));
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
  margin: 0 0 10px;
  font-size: clamp(1.05rem, 2vw, 1.35rem);
  font-weight: 600;
  line-height: 1.25;
  letter-spacing: -0.03em;
  color: #000;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

html[data-theme="dark"] .login-feature-scroll__title {
  color: #e0e0e8;
}

.login-feature-scroll__stat {
  margin: 0 0 8px;
  font-size: clamp(10px, 0.95vw, 11.5px);
  line-height: 1.5;
  color: #888;
  letter-spacing: 0.01em;
}

html[data-theme="dark"] .login-feature-scroll__stat {
  color: #8a8a96;
}

.login-feature-scroll__stat--multi {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 6px;
}

.login-feature-scroll__stat-sep {
  opacity: 0.55;
}

.login-feature-scroll__stat-num {
  display: inline-block;
  min-width: 0.6em;
  margin: 0 2px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  color: var(--platform-accent);
}

.login-feature-scroll__body {
  margin: 0;
  font-size: clamp(12px, 1vw, 13.5px);
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
}

/* ---------- split layout ---------- */
.login-feature-scroll__split {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: clamp(36px, 4vw, 64px);
  margin-top: 9px;
}

.login-feature-scroll__split .login-feature-scroll__text {
  flex: 0 1 36%;
  width: auto;
  max-width: 26em;
}

.login-feature-scroll__split .login-feature-scroll__image-wrapper {
  flex: 1 1 58%;
  width: 100%;
  max-width: min(560px, 58%);
}

.login-feature-scroll__image-backplate {
  position: relative;
  padding: 12px;
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
  border-radius: 14px;
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

/* 图片与视频共用同一媒体框尺寸（约 16:10） */
.login-feature-scroll__media,
.login-feature-scroll__video {
  position: relative;
  z-index: 2;
  width: 100%;
  aspect-ratio: 16 / 10;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.06);
  background: #111;
}

html[data-theme="dark"] .login-feature-scroll__media,
html[data-theme="dark"] .login-feature-scroll__video {
  border-color: rgba(255, 255, 255, 0.08);
}

.login-feature-scroll__img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  border: 0;
  background: #fff;
  position: relative;
  z-index: 2;
}

html[data-theme="dark"] .login-feature-scroll__img {
  background: #1a1a24;
}

.login-feature-scroll__video iframe,
.login-feature-scroll__video video {
  display: block;
  width: 100%;
  height: 100%;
  border: 0;
  object-fit: cover;
  background: #111;
}

.login-feature-scroll__video-poster {
  appearance: none;
  position: absolute;
  inset: 0;
  z-index: 3;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: 14px;
  background: #111;
  cursor: pointer;
  overflow: hidden;
}

.login-feature-scroll__video-poster-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.login-feature-scroll__video-play {
  position: relative;
  z-index: 1;
  width: 0;
  height: 0;
  margin-left: 4px;
  border-style: solid;
  border-width: 9px 0 9px 15px;
  border-color: transparent transparent transparent #fff;
  filter: drop-shadow(0 1px 4px rgba(0, 0, 0, 0.35));
  transition: transform 0.18s ease;
}

.login-feature-scroll__video-poster:hover .login-feature-scroll__video-play {
  transform: scale(1.08);
}

.login-feature-scroll__cta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}

.login-feature-scroll__cta-row .login-feature-scroll__enterprise-link {
  margin-top: 0;
}

.login-feature-scroll__enterprise-link--primary {
  background: var(--platform-accent);
  color: #fff;
}

.login-feature-scroll__enterprise-link--primary:hover {
  background: color-mix(in srgb, var(--platform-accent) 88%, #000);
  transform: translateX(3px);
}

html[data-theme="dark"] .login-feature-scroll__enterprise-link--primary {
  background: var(--platform-accent);
  color: #fff;
}

html[data-theme="dark"] .login-feature-scroll__enterprise-link--primary:hover {
  background: color-mix(in srgb, var(--platform-accent) 88%, #fff);
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
  font-size: 13px;
  color: #000;
}

html[data-theme="dark"] .login-feature-scroll__feature-title {
  color: #e0e0e8;
}

.login-feature-scroll__feature-body {
  margin: 0;
  font-size: 11px;
  line-height: 1.55;
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
  margin-top: 40px;
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
  font-size: 13px;
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
  font-size: 12px;
  color: #999;
}

html[data-theme="dark"] .login-feature-scroll__testimonial-author {
  color: #888;
}

/* ---------- acknowledgments ---------- */
.login-feature-scroll__section--acknowledgments {
  padding-bottom: 60px;
}

.login-feature-scroll__acknowledgments-title {
  text-align: center;
  margin-bottom: 8px;
}

.login-feature-scroll__acknowledgments-subtitle {
  margin: 0 auto 28px;
  max-width: 34em;
  font-size: clamp(12px, 1vw, 14px);
  font-weight: 400;
  line-height: 1.6;
  text-align: center;
  color: #666;
}

html[data-theme="dark"] .login-feature-scroll__acknowledgments-subtitle {
  color: #999;
}

.login-feature-scroll__acknowledgments-grid {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 12px;
  max-width: 960px;
  margin: 0 auto;
}

.login-feature-scroll__acknowledgment-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-width: 120px;
  padding: 16px 22px;
  border-radius: var(--platform-card-radius);
  background: var(--platform-card-bg);
  border: 1px solid var(--platform-card-border-color);
  text-decoration: none;
  transition: var(--platform-card-transition);
}

html[data-theme="dark"] .login-feature-scroll__acknowledgment-card {
  background: var(--platform-card-bg);
  border-color: var(--platform-card-border-color);
}


/* ---------- card flip animation ---------- */
.login-feature-scroll__section--visible .login-feature-scroll__acknowledgment-card {
  animation: ack-flip-in 0.55s cubic-bezier(0.22, 1, 0.36, 1) backwards;
}

@keyframes ack-flip-in {
  0% {
    opacity: 0;
    transform: perspective(600px) rotateY(90deg) scale(0.85);
  }
  100% {
    opacity: 1;
    transform: perspective(600px) rotateY(0deg) scale(1);
  }
}

.login-feature-scroll__acknowledgment-name {
  font-size: 13px;
  line-height: 1.3;
  color: #111;
  white-space: nowrap;
}

html[data-theme="dark"] .login-feature-scroll__acknowledgment-name {
  color: #e0e0e8;
}

.login-feature-scroll__acknowledgment-desc {
  font-size: 10px;
  line-height: 1.4;
  color: #999;
  text-align: center;
  max-width: 140px;
}

html[data-theme="dark"] .login-feature-scroll__acknowledgment-desc {
  color: #777;
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
  font-size: 13px;
  line-height: 1.55;
  border-radius: 10px;
  overflow: hidden;
}

.login-feature-scroll__compare-table thead th {
  padding: 10px 12px 12px;
  font-size: 12px;
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
  font-size: 14px;
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
  font-size: 13px;
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
  font-size: 10px;
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

/* ---------- enterprise link ---------- */
.login-feature-scroll__enterprise-link {
  appearance: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 16px;
  padding: 7px 14px;
  border: none;
  border-radius: 8px;
  background: color-mix(in srgb, var(--platform-accent) 10%, transparent);
  color: var(--platform-accent);
  font-size: 12px;
  cursor: pointer;
  transition:
    background 0.2s ease,
    transform 0.18s var(--platform-ease-smooth);
}

.login-feature-scroll__enterprise-link:hover {
  background: color-mix(in srgb, var(--platform-accent) 16%, transparent);
  transform: translateX(3px);
}

html[data-theme="dark"] .login-feature-scroll__enterprise-link {
  background: color-mix(in srgb, var(--platform-accent) 14%, transparent);
}

html[data-theme="dark"] .login-feature-scroll__enterprise-link:hover {
  background: color-mix(in srgb, var(--platform-accent) 22%, transparent);
}

/* ---------- responsive ---------- */
@media (max-width: 1024px) {
  .login-feature-scroll__split {
    gap: 40px;
  }

  .login-feature-scroll__split .login-feature-scroll__image-wrapper {
    max-width: min(520px, 62%);
  }
}

@media (max-width: 900px) {
  .login-feature-scroll__section {
    padding-inline: max(48px, env(safe-area-inset-left, 0px)) max(48px, env(safe-area-inset-right, 0px));
  }

  .login-feature-scroll__split {
    flex-direction: column;
    align-items: stretch;
    gap: 28px;
  }

  .login-feature-scroll__split .login-feature-scroll__text,
  .login-feature-scroll__split .login-feature-scroll__image-wrapper {
    flex: 1 1 auto;
    max-width: 100%;
    width: 100%;
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
    font-size: 12px;
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
    padding: 10px;
    border-radius: 12px;
  }

  .login-feature-scroll__media,
  .login-feature-scroll__video {
    border-radius: 8px;
  }

  .login-feature-scroll__features-grid {
    grid-template-columns: 1fr;
    gap: 6px;
  }

  .login-feature-scroll__acknowledgment-card {
    min-width: 100px;
    padding: 12px 16px;
  }

  .login-feature-scroll__acknowledgment-name {
    font-size: 12px;
  }

  .login-feature-scroll__acknowledgment-desc {
    font-size: 10px;
    max-width: 110px;
  }

  .login-feature-scroll__testimonial {
    padding: 14px 16px;
  }

  .login-feature-scroll__testimonial-quote {
    font-size: 12px;
  }

  .login-feature-scroll__footer {
    padding: 28px 14px 14px;
  }

  .login-feature-scroll__footer-links {
    gap: 6px 14px;
  }

  .login-feature-scroll__footer-link {
    font-size: 12px;
  }

  .login-feature-scroll__compare-table thead th {
    padding: 8px 6px;
    font-size: 11px;
  }

  .login-feature-scroll__compare-table tbody th,
  .login-feature-scroll__compare-table tbody td {
    padding: 7px 6px;
    font-size: 12px;
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
    font-size: 12px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .login-feature-scroll__inner,
  .login-feature-scroll__footer {
    opacity: 1 !important;
    transform: none !important;
    transition: none !important;
  }

  .login-feature-scroll__acknowledgment-card {
    animation: none !important;
    opacity: 1 !important;
    transform: none !important;
  }
}
</style>
