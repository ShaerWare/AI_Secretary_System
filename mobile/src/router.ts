import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      redirect: "/chats",
    },
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/LoginView.vue"),
      meta: { public: true },
    },
    {
      path: "/chats",
      name: "chats",
      component: () => import("@/views/ChatListView.vue"),
    },
    {
      path: "/chat/:id",
      name: "chat",
      component: () => import("@/views/ChatView.vue"),
    },
    {
      path: "/settings",
      name: "settings",
      component: () => import("@/views/SettingsView.vue"),
    },
  ],
});

router.beforeEach((to) => {
  if (to.meta.public) return;
  const auth = useAuthStore();
  if (!auth.isAuthenticated || auth.isTokenExpired()) {
    return { name: "login" };
  }
});

export default router;
