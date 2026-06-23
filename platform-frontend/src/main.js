import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import { setAppRouter } from "./utils/routerInstance.js";
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
  app.use(router);
  app.mount("#app");
}

bootstrap();
