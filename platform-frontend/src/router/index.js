import { createRouter, createWebHistory } from "vue-router";
import { getToken } from "../api/client";
import { useAuth } from "../composables/useAuth";
import { routeMenuKey, useMenuSettings } from "../composables/useMenuSettings";

const routes = [
  {
    path: "/login",
    name: "login",
    component: () => import("../views/LoginView.vue"),
    meta: { public: true },
  },
  {
    path: "/",
    component: () => import("../layouts/MainLayout.vue"),
    children: [
      { path: "", redirect: { name: "ai-home" } },
      {
        path: "ai-home",
        name: "ai-home",
        meta: { title: "AI 助理", fullHeight: true, featureIcon: "sparkles", videoBg: true, keepAlive: true },
        component: () => import("../views/AiHomeView.vue"),
      },
      {
        path: "chat-history/:scope",
        name: "chat-history",
        meta: { title: "历史对话", featureIcon: "chatbubbles", videoBg: true },
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
        meta: { title: "智能问数", fullHeight: true, featureIcon: "stats-chart", videoBg: true, keepAlive: true },
        component: () => import("../views/SmartDataQueryV2View.vue"),
      },
      {
        path: "system/data-analysis",
        name: "data-analysis",
        meta: { title: "数据分析", fullHeight: true, featureIcon: "stats-chart", keepAlive: true },
        component: () => import("../views/DataAnalysisView.vue"),
      },
      {
        path: "system/smart-data-query-v2",
        redirect: { name: "smart-data-query" },
      },
      {
        path: "system/carbon-qa",
        name: "carbon-qa",
        meta: { title: "双碳问答", fullHeight: true, featureIcon: "chatbubbles", videoBg: true, keepAlive: true },
        component: () => import("../views/CarbonQaV2View.vue"),
      },
      {
        path: "system/carbon-assets",
        name: "carbon-assets",
        meta: { title: "碳资产管理与交易", fullHeight: true, featureIcon: "wallet" },
        component: () => import("../views/CarbonAssetTradingView.vue"),
      },
      {
        path: "system/carbon-assets/history",
        name: "carbon-assets-history",
        meta: {
          title: "CEA 历史走势",
          fullHeight: true,
          featureIcon: "stats-chart",
          backTo: "carbon-assets",
        },
        component: () => import("../views/CarbonMarketHistoryView.vue"),
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
        meta: { title: "网站收藏", fullHeight: true, featureIcon: "newspaper" },
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
        meta: { title: "会议助手", fullHeight: true, featureIcon: "mic" },
        component: () => import("../views/SpeechToTextView.vue"),
      },
      {
        path: "system/ocr",
        name: "ocr",
        meta: { title: "文件内容提取", fullHeight: true, featureIcon: "scan" },
        component: () => import("../views/OcrView.vue"),
      },
      {
        path: "system/kg-palantir",
        name: "kg-palantir",
        meta: {
          title: "Palantir与知识图谱",
          fullHeight: true,
          featureIcon: "git-network",
          perm: "feature.kg_palantir",
          keepAlive: true,
        },
        component: () => import("../views/KgPalantirView.vue"),
      },
      {
        path: "system/compare",
        name: "compare",
        meta: { title: "文档对比", fullHeight: true, featureIcon: "git-compare" },
        component: () => import("../views/CompareView.vue"),
      },
      {
        path: "system/assist-writing",
        name: "assist-writing",
        meta: { title: "辅助写作", fullHeight: true, featureIcon: "create" },
        component: () => import("../views/AssistWritingView.vue"),
      },
      {
        path: "system/pageindex",
        redirect: { name: "knowledge-search" },
      },
      {
        path: "system/report-generation",
        name: "report-generation",
        meta: {
          title: "报告生成",
          fullHeight: true,
          flushStart: true,
          flushEnd: true,
          featureIcon: "document-text",
          keepAlive: true,
          videoBg: true,
        },
        component: () => import("../views/ReportGenerationView.vue"),
      },
      {
        path: "knowledge-graph",
        redirect: { name: "documents" },
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
          videoBg: true,
        },
        component: () => import("../views/KnowledgeSearchView.vue"),
      },
      {
        path: "documents",
        name: "documents",
        meta: { title: "文档中心", featureIcon: "document-text" },
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
        meta: { title: "模型配置", featureLocalNav: true },
        component: () => import("../views/admin/ModelSettingsView.vue"),
      },
      {
        path: "admin/menu-settings",
        name: "admin-menu-settings",
        meta: { title: "菜单管理", perm: "admin.user" },
        component: () => import("../views/admin/MenuSettingsView.vue"),
      },
      {
        path: "admin/docs",
        name: "admin-docs",
        meta: { title: "说明文档" },
        component: () => import("../views/admin/SystemDocsView.vue"),
      },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
});

router.beforeEach(async (to) => {
  if (to.meta.public) return true;
  if (!getToken()) return { name: "login", query: { redirect: to.fullPath } };
  const { loadUser, hasPerm, user } = useAuth();
  if (!user.value) await loadUser();
  if (!getToken()) return { name: "login", query: { redirect: to.fullPath } };
  if (to.meta.perm && !hasPerm(to.meta.perm)) {
    return { name: "ai-home" };
  }
  if (user.value && !user.value.is_system_admin) {
    const { loadMenuSettings, isMenuVisible, firstVisibleRouteName } = useMenuSettings();
    await loadMenuSettings();
    const menuKey = routeMenuKey(String(to.name || ""));
    if (menuKey && !isMenuVisible(menuKey)) {
      return { name: firstVisibleRouteName() };
    }
  }
  return true;
});

export default router;
