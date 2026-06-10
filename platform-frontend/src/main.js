import { createApp } from "vue";
import naive from "naive-ui";
import App from "./App.vue";
import router from "./router";
import { useAppPreferences, initAppFromServerConfig } from "./composables/useAppPreferences";
import { applyClientBranding } from "./composables/usePlatformBranding";
import { bootstrapClientConfig } from "./api/http";

async function bootstrap() {
  const config = await bootstrapClientConfig();
  if (config) {
    applyClientBranding(config);
    initAppFromServerConfig(config);
  }
  useAppPreferences();

  const app = createApp(App);
  app.use(naive);
  app.use(router);
  app.mount("#app");
}

bootstrap();
