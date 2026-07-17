import { createRouter, createWebHistory } from "vue-router";
import { getToken } from "../api/client";
import { beginRouteRequestScope } from "../api/requestScope.js";
import { useAuth } from "../composables/useAuth";
import { routeMenuKey, useMenuSettings, isConfigurableMenuKey } from "../composables/useMenuSettings";
import { useSystemFeatures } from "../composables/useSystemFeatures";
import { DEFAULT_HOME_ROUTE } from "../utils/postLoginRoute.js";
import { releaseRouteMemory } from "../utils/routeMemoryCleanup.js";
import { cleanupBlockingUiArtifacts } from "../utils/blockingUiCleanup.js";
import { reportWebVital } from "../utils/perfMetrics.js";

const routes = [
  {
    path: "/login",
    name: "login",
    component: () => import("../views/LoginView.vue"),
    meta: { public: true },
  },
  {
    path: "/privacy",
    name: "privacy",
    component: () => import("../views/LegalPagesView.vue"),
    meta: { public: true, title: "隐私政策" },
  },
  {
    path: "/terms",
    name: "terms",
    component: () => import("../views/LegalPagesView.vue"),
    meta: { public: true, title: "服务协议" },
  },
  {
    path: "/enterprise/knowledge",
    name: "enterprise-knowledge",
    component: () => import("../views/EnterprisePromoView.vue"),
    meta: { public: true, title: "企业级知识检索与报告生成" },
  },
  {
    path: "/agentkit-philosophy",
    name: "agentkit-philosophy",
    meta: { public: true, title: "AgentKit 设计哲学" },
    component: () => import("../views/AgentkitPhilosophyView.vue"),
  },
  {
    path: "/",
    component: () => import("../layouts/MainLayout.vue"),
    children: [
      { path: "", redirect: { name: "ai-home" } },
      {
        path: "ai-home",
        name: "ai-home",
        meta: { title: "本析智能", fullHeight: true, featureIcon: "sparkles", keepAlive: true },
        component: () => import("../views/AiHomeView.vue"),
      },
      {
        path: "ai-home/tab/:tabId",
        name: "ai-home-tab",
        meta: { title: "本析智能", fullHeight: true, featureIcon: "sparkles", keepAlive: true },
        component: () => import("../views/AiHomeView.vue"),
      },
      {
        path: "chat-history/:scope",
        name: "chat-history",
        meta: { title: "历史对话", featureIcon: "chatbubbles" },
        component: () => import("../views/ChatHistoryView.vue"),
      },
      {
        path: "system/functions",
        name: "system-functions",
        meta: { title: "功能列表", featureIcon: "grid" },
        component: () => import("../views/SystemFunctionsView.vue"),
      },
      {
        path: "system/ai-tools",
        name: "ai-tools",
        meta: { title: "在线 AI 工具", featureIcon: "sparkles" },
        component: () => import("../views/AiToolsView.vue"),
      },
      {
        path: "system/translate",
        name: "translate",
        meta: { title: "PDF 翻译", fullHeight: true, featureIcon: "language" },
        component: () => import("../views/TranslateView.vue"),
      },
      {
        path: "system/smart-data-query",
        name: "smart-data-query",
        meta: { title: "智能问数", fullHeight: true, featureIcon: "stats-chart" },
        component: () => import("../views/SmartDataQueryV2View.vue"),
      },
      {
        path: "system/data-analysis",
        name: "data-analysis",
        meta: { title: "数据分析", fullHeight: true, featureIcon: "stats-chart" },
        component: () => import("../views/DataAnalysisView.vue"),
      },
      {
        path: "system/smart-data-query-v2",
        redirect: { name: "smart-data-query" },
      },
      {
        path: "system/carbon-qa",
        name: "carbon-qa",
        meta: { title: "双碳问答", fullHeight: true, featureIcon: "chatbubbles" },
        component: () => import("../views/CarbonQaV2View.vue"),
      },
      {
        path: "system/wechat-mp",
        redirect: { name: "knowledge-subscriptions" },
      },
      {
        path: "system/wechat-mp/articles/:id",
        redirect: { name: "knowledge-subscriptions" },
      },
      {
        path: "knowledge/subscriptions",
        name: "knowledge-subscriptions",
        meta: { title: "资讯管理", fullHeight: true, featureIcon: "newspaper" },
        component: () => import("../views/SubscriptionsView.vue"),
      },
      {
        path: "knowledge/subscriptions/items/:ref",
        name: "subscription-item",
        meta: {
          title: "资讯详情",
          fullHeight: true,
          featureIcon: "newspaper",
          backTo: "knowledge-subscriptions",
        },
        component: () => import("../views/SubscriptionItemView.vue"),
      },
      {
        path: "knowledge/wechat-mp",
        redirect: { name: "knowledge-subscriptions" },
      },
      {
        path: "knowledge/wechat-mp/articles/:id",
        redirect: { name: "knowledge-subscriptions" },
      },
      {
        path: "knowledge/feed-subscriptions",
        redirect: { name: "knowledge-subscriptions" },
      },
      {
        path: "knowledge/feed-subscriptions/entries/:id",
        redirect: { name: "knowledge-subscriptions" },
      },
      {
        path: "system/carbon-qa-v2",
        redirect: { name: "carbon-qa" },
      },
      {
        path: "system/smart-forecast",
        name: "smart-forecast",
        meta: {
          title: "智能预测",
          fullHeight: true,
          featureIcon: "stats-chart",
          embedFeatureId: "smart_forecast",
        },
        component: () => import("../views/FeatureEmbedView.vue"),
      },
      {
        path: "system/speech",
        name: "speech",
        meta: { title: "语音转写", fullHeight: true, featureIcon: "mic" },
        component: () => import("../views/SpeechToTextView.vue"),
      },
      {
        path: "system/text-to-speech",
        name: "text-to-speech",
        meta: { title: "语音合成", fullHeight: true, featureIcon: "volume-high" },
        component: () => import("../views/TextToSpeechView.vue"),
      },
      {
        path: "system/ocr",
        name: "ocr",
        meta: { title: "文件内容提取", fullHeight: true, featureIcon: "scan" },
        component: () => import("../views/OcrView.vue"),
      },
      {
        path: "system/ontology",
        name: "ontology",
        meta: {
          title: "本体定义",
          fullHeight: true,
          flushStart: true,
          flushEnd: true,
          featureIcon: "git-network",
          perm: "feature.ontology",
        },
        component: () => import("../views/OntologyView.vue"),
      },
      {
        path: "system/kg",
        name: "kg",
        meta: {
          title: "知识图谱",
          fullHeight: true,
          flushStart: true,
          flushEnd: true,
          featureIcon: "cube-outline",
          perm: "feature.kg",
        },
        component: () => import("../views/KgView.vue"),
      },
      {
        path: "system/compare",
        name: "compare",
        meta: { title: "文档对比", fullHeight: true, featureIcon: "git-compare" },
        component: () => import("../views/CompareView.vue"),
      },
      {
        path: "knowledge/search",
        name: "knowledge-search",
        meta: {
          title: "知识检索",
          fullHeight: true,
          flushStart: true,
          flushEnd: true,
          featureIcon: "search",
          backTo: "ai-home",
          perm: "feature.knowledge_search",
          keepAlive: true,
        },
        component: () => import("../layouts/KnowledgeFeatureLayout.vue"),
      },
      {
        path: "knowledge/report",
        name: "report-generation",
        meta: {
          title: "报告生成",
          fullHeight: true,
          flushStart: true,
          flushEnd: true,
          featureIcon: "create",
          keepAlive: true,
        },
        component: () => import("../layouts/KnowledgeFeatureLayout.vue"),
      },
      {
        path: "system/pageindex",
        redirect: { name: "knowledge-search" },
      },
      {
        path: "system/report-generation",
        redirect: { name: "report-generation" },
      },
      {
        path: "knowledge-graph",
        redirect: { name: "documents" },
      },
      {
        path: "documents",
        name: "documents",
        meta: { title: "我的文件", featureIcon: "document-text", keepAlive: true },
        component: () => import("../views/DocumentsView.vue"),
      },
      {
        path: "documents/recycle",
        redirect: { name: "documents" },
      },
      {
        path: "documents/:id",
        name: "document-detail",
        meta: {
          title: "文档详情",
          featureIcon: "document-text",
          backTo: "documents",
        },
        component: () => import("../views/DocumentDetailView.vue"),
        beforeEnter: (to) => {
          const id = String(to.params.id || "");
          const uuid =
            /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
          if (!uuid.test(id)) {
            if (id === "recycle") {
              return { name: "documents" };
            }
            return { name: "documents" };
          }
          return true;
        },
      },
      {
        path: "jobs",
        name: "jobs",
        meta: { title: "后台任务" },
        component: () => import("../views/JobsView.vue"),
      },
      {
        path: "notifications",
        name: "notifications",
        meta: { title: "消息通知", featureIcon: "notifications" },
        component: () => import("../views/NotificationsView.vue"),
      },
      {
        path: "todos",
        name: "todos",
        meta: { title: "待办事项", featureIcon: "list" },
        component: () => import("../views/TodosView.vue"),
      },
      {
        path: "profile",
        name: "profile",
        meta: { title: "信息维护", featureIcon: "settings" },
        component: () => import("../views/ProfileView.vue"),
      },
      {
        path: "admin/users",
        name: "admin-users",
        meta: { title: "用户管理", perm: "admin.user" },
        component: () => import("../views/admin/UsersView.vue"),
      },
      {
        path: "admin/departments",
        name: "admin-departments",
        meta: { title: "部门管理", perm: "admin.dept" },
        component: () => import("../views/admin/DepartmentsView.vue"),
      },
      {
        path: "admin/monitor",
        name: "admin-monitor",
        meta: { title: "系统监控" },
        component: () => import("../views/admin/SystemMonitorView.vue"),
      },
      {
        path: "admin/model-settings",
        name: "admin-model-settings",
        meta: { title: "资源管理", perm: "admin.user", featureLocalNav: true },
        component: () => import("../views/admin/ModelSettingsView.vue"),
      },
      {
        path: "system/agent-skills",
        name: "agent-skills",
        meta: {
          title: "多智能体",
          perm: "feature.agent_skills",
          featureIcon: "extension-puzzle",
          featureLocalNav: true,
          keepAlive: true,
        },
        component: () => import("../views/admin/AgentSkillsView.vue"),
      },
      {
        path: "system/aip-keys",
        redirect: { name: "agent-skills", query: { tab: "aip-keys" } },
      },
      {
        path: "admin/agent-skills",
        redirect: { name: "agent-skills" },
      },
      {
        path: "admin/menu-settings",
        name: "admin-menu-settings",
        meta: { title: "菜单管理", perm: "admin.user" },
        component: () => import("../views/admin/MenuSettingsView.vue"),
      },
      {
        path: "issue-reports",
        name: "issue-reports",
        meta: { title: "改进建议", featureIcon: "list" },
        component: () => import("../views/IssueReportsView.vue"),
      },
      {
        path: "agentkit-docs",
        name: "agentkit-docs",
        meta: { title: "AgentKit 架构" },
        component: () => import("../views/AgentkitDocsView.vue"),
      },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
});

/** 默认首页与对话历史：不受「菜单可见性」拦截，确保登录后可达 AI 智能体 */
const MENU_VISIBILITY_EXEMPT = new Set(["ai-home", "ai-home-tab", "chat-history"]);

router.beforeEach(async (to) => {
  beginRouteRequestScope();
  if (to.meta.public) {
    if (to.name === "login" && getToken()) {
      const { loadUser } = useAuth();
      await loadUser();
      if (getToken()) {
        return DEFAULT_HOME_ROUTE;
      }
    }
    return true;
  }
  if (!getToken()) return { name: "login" };
  const { loadUser, hasPerm, user } = useAuth();
  if (!user.value) await loadUser();
  if (!getToken() || !user.value) return { name: "login" };
  if (to.meta.perm && !hasPerm(to.meta.perm)) {
    return DEFAULT_HOME_ROUTE;
  }
  if (user.value) {
    const { isMenuVisible, firstVisibleRouteName } = useMenuSettings();
    const { loadSystemFeatures } = useSystemFeatures();
    await loadSystemFeatures();
    const menuKey = routeMenuKey(String(to.name || ""));
    // 有 perm 检查的路由由 hasPerm 保护，不需要额外做菜单可见性拦截。
    // 侧栏已用 isMenuVisible 控制渲染，用户点不到被隐藏的菜单项；
    // 直接输 URL 的场景由 hasPerm 提供安全防护，菜单可见性检查是冗余的。
    if (
      !to.meta.perm &&
      menuKey &&
      isConfigurableMenuKey(menuKey) &&
      !MENU_VISIBILITY_EXEMPT.has(String(to.name || "")) &&
      !isMenuVisible(menuKey)
    ) {
      return { name: firstVisibleRouteName() };
    }
  }
  return true;
});

router.afterEach((to, from) => {
  sessionStorage.removeItem("platform:chunk-reload");
  cleanupBlockingUiArtifacts({ aggressive: true });
  if (from.meta?.public) return;
  releaseRouteMemory(from, to);
  /* 预取高频路由块：登录后/首页加载后尽早拉取「我的文件」「多智能体」chunk */
  _prefetchPopularChunksIfNeeded(to);
  /* 性能指标采集 */
  reportPerfMetricsOnRoute(to);
});

/** 路由切换后采集 Web Vitals 性能指标 */
function reportPerfMetricsOnRoute(to) {
  if (to.meta?.public || to.name === "login") return;
  if (typeof window.requestIdleCallback === "function") {
    requestIdleCallback(
      () => {
        reportWebVital({ routeName: String(to.name || "") });
      },
      { timeout: 3000 }
    );
  } else {
    setTimeout(() => {
      reportWebVital({ routeName: String(to.name || "") });
    }, 2000);
  }
}

/** 高频路由块地址表（与 routes 中的 import() 一致） */
const _POPULAR_CHUNKS = [
  () => import("../views/DocumentsView.vue"),
  () => import("../views/admin/AgentSkillsView.vue"),
];
let _chunksPrefetched = false;

function _prefetchPopularChunksIfNeeded(to) {
  if (_chunksPrefetched) return;
  if (!to.meta?.public && to.name !== "login") {
    _chunksPrefetched = true;
    for (const imp of _POPULAR_CHUNKS) {
      imp().catch(() => {});
    }
  }
}

/** 发版后浏览器仍缓存旧 chunk 时，自动刷新一次以拉取新 index / assets */
router.onError((error, _to) => {
  const msg = String(error?.message || error || "");
  const isChunkLoadError =
    msg.includes("Failed to fetch dynamically imported module") ||
    msg.includes("Importing a module script failed") ||
    msg.includes("error loading dynamically imported module");
  if (!isChunkLoadError) return;
  if (sessionStorage.getItem("platform:chunk-reload")) return;
  sessionStorage.setItem("platform:chunk-reload", "1");
  window.location.reload();
});

export default router;
