<script setup>
import { ref } from "vue";
import { platformCopyrightText } from "../constants/platform";
import { useI18n } from "../composables/useI18n";

const { t } = useI18n();
const BASE = import.meta.env.BASE_URL.replace(/\/+$/, "");

defineProps({
  compact: { type: Boolean, default: false },
});

const coffeeModalOpen = ref(false);

function openCoffeeModal() {
  coffeeModalOpen.value = true;
}
</script>

<template>
  <div
    class="platform-copyright"
    :class="{ 'platform-copyright--compact': compact }"
  >
    <p class="coffee-invite" @click="openCoffeeModal">☕ 请开发者喝咖啡～</p>
    <p :title="platformCopyrightText()">{{ platformCopyrightText() }}</p>
  </div>

  <n-modal
    :show="coffeeModalOpen"
    preset="card"
    class="coffee-modal"
    :style="{ width: 'min(440px, calc(100vw - 38px))' }"
    :mask-closable="true"
    transform-origin="center"
    @update:show="coffeeModalOpen = $event"
  >
    <template #header>
      <div class="coffee-modal__header">
        <span class="coffee-modal__emoji">☕</span>
        <div>
          <h2 class="coffee-modal__title">{{ t("login.buyCoffee") }}</h2>
        </div>
      </div>
    </template>
    <div class="coffee-modal__body">
      <p class="coffee-modal__desc">{{ t("login.buyCoffeeDesc") }}</p>
      <div class="coffee-modal__qrcodes">
        <div class="coffee-modal__qrcode">
          <img :src="`${BASE}/images/coffee-wechat.jpg`" alt="微信收款码" width="160" />
          <span class="coffee-modal__qrcode-label">微信</span>
        </div>
        <div class="coffee-modal__qrcode">
          <img :src="`${BASE}/images/coffee-alipay.jpg`" alt="支付宝收款码" width="160" />
          <span class="coffee-modal__qrcode-label">支付宝</span>
        </div>
      </div>
    </div>
  </n-modal>
</template>

<style scoped>
.platform-copyright {
  margin: 0;
  padding: 12px 17px 14px;
  text-align: center;
  color: var(--platform-text-quaternary);
  word-break: break-word;
}

.platform-copyright p {
  margin: 0;
  font-size: 13px;
  line-height: 1.45;
}

.platform-copyright .coffee-invite {
  margin-bottom: 4px;
  font-size: 13px;
  line-height: 1.45;
  cursor: pointer;
  transition: color 0.2s;
}

.platform-copyright .coffee-invite:hover {
  color: var(--platform-text-tertiary);
}

.platform-copyright--compact {
  padding: 7px 10px 10px;
}

.platform-copyright--compact p {
  font-size: 12px;
  line-height: 1.35;
}

.platform-copyright--compact .coffee-invite {
  margin-bottom: 3px;
  font-size: 12px;
  line-height: 1.35;
}
</style>

<style>
/* Modal styles (non-scoped to work with teleport to body) */
.coffee-modal .n-card-header__main {
  display: flex;
  align-items: center;
}
.coffee-modal__header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.coffee-modal__header > div {
  flex: 1;
}
.coffee-modal__emoji {
  font-size: 28px;
  line-height: 1;
}
.coffee-modal__title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--platform-text);
}
.coffee-modal__body {
  text-align: center;
}
.coffee-modal__desc {
  margin: 0 0 16px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--platform-text-secondary);
}
.coffee-modal__qrcodes {
  display: flex;
  justify-content: center;
  gap: 24px;
}
.coffee-modal__qrcode {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.coffee-modal__qrcode img {
  border-radius: 8px;
  display: block;
}
.coffee-modal__qrcode-label {
  font-size: 12px;
  color: var(--platform-text-tertiary);
}
</style>
