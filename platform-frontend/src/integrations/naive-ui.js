/**
 * naive-ui 入口 shim：NSpin / NBaseLoading 统一替换为 Rose Three。
 */
import naiveDefault from "../../node_modules/naive-ui/es/index.mjs";
import PlatformSpin from "../components/PlatformSpin.vue";
import PlatformBaseLoading from "../components/PlatformBaseLoading.vue";

const originalInstall = naiveDefault.install?.bind(naiveDefault);
if (originalInstall) {
  naiveDefault.install = (app, options) => {
    originalInstall(app, options);
    app.component("NSpin", PlatformSpin);
  };
}

export default naiveDefault;
export * from "../../node_modules/naive-ui/es/index.mjs";
export { default as NSpin } from "../components/PlatformSpin.vue";
