import { createRouter, createWebHistory } from "vue-router";
import { getToken } from "../api/client";
import { useAuth } from "../composables/useAuth";

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
      { path: "", redirect: "/documents" },
      {
        path: "system/functions",
        name: "system-functions",
        meta: { title: "系统功能" },
        component: () => import("../views/SystemFunctionsView.vue"),
      },
      {
        path: "system/translate",
        name: "translate",
        meta: { title: "PDF 翻译" },
        component: () => import("../views/TranslateView.vue"),
      },
      {
        path: "documents",
        name: "documents",
        component: () => import("../views/DocumentsView.vue"),
      },
      {
        path: "documents/:id",
        name: "document-detail",
        component: () => import("../views/DocumentDetailView.vue"),
      },
      {
        path: "jobs",
        name: "jobs",
        component: () => import("../views/JobsView.vue"),
      },
      {
        path: "notifications",
        name: "notifications",
        component: () => import("../views/NotificationsView.vue"),
      },
      {
        path: "admin/users",
        name: "admin-users",
        meta: { perm: "admin.user" },
        component: () => import("../views/admin/UsersView.vue"),
      },
      {
        path: "admin/departments",
        name: "admin-departments",
        meta: { perm: "admin.dept" },
        component: () => import("../views/admin/DepartmentsView.vue"),
      },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to) => {
  if (to.meta.public) return true;
  if (!getToken()) return { name: "login", query: { redirect: to.fullPath } };
  const { loadUser, hasPerm, user } = useAuth();
  if (!user.value) await loadUser();
  if (to.meta.perm && !hasPerm(to.meta.perm)) {
    return { name: "documents" };
  }
  return true;
});

export default router;
