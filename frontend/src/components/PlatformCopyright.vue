<script setup>
import { useI18n } from "../composables/useI18n";
import { openExternal } from "../utils/openExternal";

const { t } = useI18n();

defineProps({
  compact: { type: Boolean, default: false },
  /** 暂时可关闭「打赏开发者」入口 */
  showBuyCoffee: { type: Boolean, default: true },
});

const emit = defineEmits(["coffeeClick"]);

const HAIYI_HOMEPAGE = "https://www.haiyisoft.com";

function onCoffeeClick() {
  emit("coffeeClick");
}
</script>

<template>
  <div
    class="platform-copyright"
    :class="{ 'platform-copyright--compact': compact }"
  >
    <p class="platform-copyright__links">
      <a class="platform-copyright__link" @click.prevent="openExternal(HAIYI_HOMEPAGE)" href="#">{{ t("copyright.about") }}</a>
      <template v-if="showBuyCoffee">
        <span class="platform-copyright__sep" aria-hidden="true">·</span>
        <button type="button" class="platform-copyright__link platform-copyright__link--btn" @click="onCoffeeClick">
          {{ t("login.buyCoffee") }}
        </button>
      </template>
    </p>
    <p>{{ t("copyright.text") }}</p>
  </div>
</template>

<style scoped>
.platform-copyright {
  margin: 0;
  padding: 12px 17px 14px;
  text-align: center;
  color: var(--platform-text-quaternary);
  word-break: break-word;
  pointer-events: auto;
}

.platform-copyright p {
  margin: 0;
  font-size: 13px;
  line-height: 1.45;
}

.platform-copyright__links {
  margin: 0 0 4px;
  font-size: 13px;
  line-height: 1.45;
}

.platform-copyright__sep {
  margin: 0 6px;
  opacity: 0.55;
}

.platform-copyright__link {
  color: var(--platform-text-quaternary);
  text-decoration: none;
  cursor: pointer;
  transition: color 0.2s;
}

.platform-copyright__link--btn {
  appearance: none;
  border: none;
  padding: 0;
  margin: 0;
  background: none;
  font: inherit;
}

.platform-copyright__link:hover {
  color: var(--platform-text-tertiary);
}

.platform-copyright--compact .platform-copyright__links {
  margin-bottom: 3px;
  font-size: 12px;
  line-height: 1.35;
}

.platform-copyright--compact {
  padding: 7px 10px 10px;
}

.platform-copyright--compact p {
  font-size: 12px;
  line-height: 1.35;
}
</style>
