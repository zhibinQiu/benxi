import { createApp } from "vue";
import App from "./App.vue";
import router from "./router/mobile.js";
import { setAppRouter } from "./utils/routerInstance.js";
import { initCrossTabSessionGuard } from "./utils/sessionGuard.js";
import { useAppPreferences, initAppFromServerConfig } from "./composables/useAppPreferences";
import { applyClientBranding } from "./composables/usePlatformBranding";
import { bootstrapClientConfig } from "./api/http";
import { ensureLocale } from "./locales";
import PlatformSpin from "./components/PlatformSpin.vue";
import RoseLoader from "./components/RoseLoader.vue";

async function bootstrap() {
  const config = await bootstrapClientConfig();
  if (config) {
    applyClientBranding(config);
    initAppFromServerConfig(config);
  }
  useAppPreferences();
  const storedLocale = localStorage.getItem("platform-locale") === "en" ? "en" : "zh";
  await ensureLocale(storedLocale);

  const app = createApp(App);
  app.component("NSpin", PlatformSpin);
  app.component("RoseLoader", RoseLoader);
  setAppRouter(router);
  initCrossTabSessionGuard();
  app.use(router);
  app.mount("#app");
  const skeleton = document.getElementById("app-skeleton");
  if (skeleton) {
    skeleton.style.opacity = "0";
    setTimeout(() => skeleton.remove(), 300);
  }
}

bootstrap();
