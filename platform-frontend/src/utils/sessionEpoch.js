/** 登录/退出时递增，用于销毁 KeepAlive 缓存的页面实例 */

import { ref } from "vue";

export const sessionEpoch = ref(0);

export function bumpSessionEpoch() {
  sessionEpoch.value += 1;
}
