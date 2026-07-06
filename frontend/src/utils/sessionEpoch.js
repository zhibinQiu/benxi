/** 登录/退出时递增，用于销毁 KeepAlive 缓存的页面实例 */

import { ref } from "vue";

export const sessionEpoch = ref(0);
/** 主动退出中为 true，用于抑制飞行中请求的鉴权错误提示 */
export const loggingOut = ref(false);

export function bumpSessionEpoch() {
  sessionEpoch.value += 1;
}
