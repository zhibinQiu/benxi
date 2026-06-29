<script setup>
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { useDialog } from "naive-ui";
import { usePlatformUi } from "../composables/usePlatformUi";
import { onSessionReplaced } from "../utils/sessionGuard";
import { withSystemDialogLayer } from "../utils/systemDialog.js";

const router = useRouter();
const dialog = useDialog();
const ui = usePlatformUi();

onMounted(() => {
  onSessionReplaced((text) => {
    ui.warning(text);
    if (router.currentRoute.value.name === "login") return;
    dialog.warning(
      withSystemDialogLayer({
        title: "登录状态已失效",
        content: text,
        positiveText: "重新登录",
        maskClosable: false,
        closeOnEsc: false,
        onPositiveClick: () => {
          router.replace({ name: "login" });
          return true;
        },
      })
    );
  });
});
</script>

<template>
  <span aria-hidden="true" style="display: none" />
</template>
