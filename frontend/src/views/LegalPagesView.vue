<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useTranslation } from "../composables/useTranslation";

const route = useRoute();
const router = useRouter();
const { t } = useTranslation();

const pageType = computed(() => route.name === "privacy" ? "privacy" : "terms");

const pageTitle = computed(() => {
  return pageType.value === "privacy"
    ? "隐私政策"
    : "服务协议";
});
</script>

<template>
  <div class="legal-page">
    <div class="legal-page__header">
      <button class="legal-page__back" @click="router.back()">← 返回</button>
      <h1 class="legal-page__title">{{ pageTitle }}</h1>
    </div>
    <div class="legal-page__body">
      <template v-if="pageType === 'privacy'">
        <section>
          <h2>一、总则</h2>
          <p>本析平台（以下简称"本平台"或"我们"）深知个人信息对用户（以下简称"您"）的重要性，我们将按照法律法规的要求，采取相应的安全保护措施，保护您的个人信息安全。请您在使用本平台服务前，仔细阅读并充分理解本《隐私政策》的全部内容。</p>
        </section>
        <section>
          <h2>二、我们如何收集和使用您的个人信息</h2>
          <p>在您使用本平台服务的过程中，我们可能会收集以下类型的个人信息：</p>
          <ol>
            <li><strong>账号信息</strong>：包括手机号码、电子邮箱、用户名和密码，用于为您创建账号并提供登录服务。</li>
            <li><strong>个人资料</strong>：您可选择提供的头像、姓名、部门等信息，用于完善您的个人主页和团队协作。</li>
            <li><strong>文档内容</strong>：您上传、翻译、分析或处理的文档和文本内容，用于为您提供核心业务功能（翻译、OCR、数据分析等）。</li>
            <li><strong>使用日志</strong>：包括操作记录、功能使用频率、错误日志等，用于优化产品体验和排查问题。</li>
            <li><strong>设备信息</strong>：包括浏览器类型、操作系统、设备型号等，用于保障服务安全与兼容性。</li>
          </ol>
        </section>
        <section>
          <h2>三、信息存储与安全</h2>
          <p>我们采取业界通行的安全技术和措施保护您的个人信息，包括但不限于：</p>
          <ul>
            <li>数据传输采用 TLS/SSL 加密协议；</li>
            <li>敏感信息在数据库中加密存储；</li>
            <li>建立严格的访问控制机制，仅授权人员可接触用户数据；</li>
            <li>定期进行安全审计和渗透测试。</li>
          </ul>
          <p>您的个人信息将仅存储在中国境内的服务器上。我们仅在为实现服务目的所必需的期限内保留您的个人信息，超出期限后将予以删除或匿名化处理。</p>
        </section>
        <section>
          <h2>四、信息共享与对外提供</h2>
          <p>我们不会将您的个人信息出售给第三方。在以下情形中，我们可能会依法共享您的信息：</p>
          <ul>
            <li>获得您的明确同意后；</li>
            <li>根据法律法规、司法或行政机关的要求；</li>
            <li>为保护本平台、用户或公众的合法权益所必要；</li>
            <li>与为我们提供服务的合作伙伴（如云服务商）共享，且该等合作伙伴需签署相应的保密协议。</li>
          </ul>
        </section>
        <section>
          <h2>五、您的权利</h2>
          <p>您享有以下个人信息相关权利：</p>
          <ul>
            <li><strong>查阅权</strong>：您可以在个人设置中查看您提供的个人信息。</li>
            <li><strong>更正权</strong>：如信息有误，您可随时在设置中更正。</li>
            <li><strong>删除权</strong>：您可以申请删除您的账号及相关信息。</li>
            <li><strong>撤回同意</strong>：您可以撤回对信息收集和使用的同意，但撤回不影响此前基于同意已进行的处理。撤回可能导致部分功能无法正常使用。</li>
          </ul>
        </section>
        <section>
          <h2>六、隐私政策更新</h2>
          <p>我们可能会根据产品迭代和法律法规的变化适时更新本政策。重大变更将以弹窗或站内通知的方式告知您。修改后的隐私政策自发布之日起生效。</p>
        </section>
        <section>
          <h2>七、联系我们</h2>
          <p>如您对本隐私政策有任何疑问、意见或投诉，请通过以下方式联系我们：</p>
          <ul>
            <li>站内反馈：改进建议页面</li>
            <li>电子邮件：privacy@benxi.com</li>
          </ul>
          <p>我们将在 15 个工作日内回复您的请求。</p>
        </section>
      </template>

      <template v-else>
        <section>
          <h2>一、协议说明</h2>
          <p>欢迎使用本析平台（以下简称"本平台"）。本《服务协议》（以下简称"本协议"）是您与本平台运营方之间关于使用本平台服务所订立的有效协议。请您在使用本平台服务前仔细阅读本协议的全部内容。如您不同意本协议的任何条款，请停止使用本平台服务。</p>
        </section>
        <section>
          <h2>二、服务内容</h2>
          <p>本平台提供包括但不限于以下服务：</p>
          <ol>
            <li>文档翻译服务（支持多语言互译）；</li>
            <li>光学字符识别（OCR）服务；</li>
            <li>文档对比分析服务；</li>
            <li>知识检索与智能问答服务；</li>
            <li>数据分析和报告生成服务；</li>
            <li>语音转写与语音合成服务；</li>
            <li>多智能体协作服务；</li>
            <li>其他本平台后续上线并明确告知的功能。</li>
          </ol>
          <p>我们保留根据业务发展需要调整、增减或终止部分服务的权利，调整前将以适当方式通知您。</p>
        </section>
        <section>
          <h2>三、用户账号</h2>
          <ul>
            <li>您注册账号时应提供真实、准确、完整的信息，并在信息变更时及时更新。</li>
            <li>您对账号下的所有行为承担全部责任，应妥善保管账号和密码，不得出借、转让或授权他人使用。</li>
            <li>如发现账号被盗用或存在安全漏洞，请立即通知我们。</li>
            <li>注册账号后如长期未使用，我们保留回收账号的权利。</li>
          </ul>
        </section>
        <section>
          <h2>四、用户行为规范</h2>
          <p>您在使用本平台服务时承诺：</p>
          <ul>
            <li>不利用本平台从事违法违规活动；</li>
            <li>不上传含有病毒、恶意代码或可能破坏系统安全的内容；</li>
            <li>不侵犯他人的知识产权、隐私权等合法权益；</li>
            <li>不利用任何自动化工具（爬虫、脚本等）非法抓取平台数据；</li>
            <li>不对本平台的系统进行逆向工程、破解或攻击。</li>
          </ul>
          <p>如您违反上述规范，我们有权采取警告、限制功能、封禁账号等措施，并保留追究法律责任的权利。</p>
        </section>
        <section>
          <h2>五、知识产权</h2>
          <ul>
            <li>本平台自身提供的软件、技术、界面设计、算法模型等知识产权归本平台所有。</li>
            <li>您上传至本平台的文档和内容，其知识产权仍归您所有。您授予本平台为提供和优化服务所必需的、免费的、非独占的使用许可。</li>
            <li>本平台利用人工智能技术生成的内容，其知识产权归属适用相关法律法规的规定。</li>
          </ul>
        </section>
        <section>
          <h2>六、免责声明</h2>
          <ul>
            <li>本平台按"现状"和"可用"的基础提供服务，不作出任何明示或暗示的保证。</li>
            <li>人工智能生成的内容仅供参考，不构成专业意见，我们不对其准确性、完整性和可靠性作出保证。</li>
            <li>因不可抗力、系统维护、第三方服务故障等原因导致的服务中断，我们不承担责任。</li>
            <li>在法律允许的最大范围内，我们对因使用本平台服务而产生的间接损失不承担责任。</li>
          </ul>
        </section>
        <section>
          <h2>七、协议变更与终止</h2>
          <p>我们可能会根据法律法规变化和业务调整修改本协议。修改后的协议将在平台公示，如您继续使用服务，视为接受修改。任何一方均可按约定终止本协议，协议终止不影响此前已产生的权利义务。</p>
        </section>
        <section>
          <h2>八、法律适用与争议解决</h2>
          <p>本协议的订立、执行和解释适用中华人民共和国法律。因本协议引起的或与本协议有关的争议，双方应友好协商解决；协商不成的，提交本平台运营方所在地有管辖权的人民法院诉讼解决。</p>
        </section>
        <section>
          <h2>九、联系我们</h2>
          <p>如您对本服务协议有任何疑问，请通过以下方式联系我们：</p>
          <ul>
            <li>站内反馈：改进建议页面</li>
            <li>电子邮件：legal@benxi.com</li>
          </ul>
        </section>
      </template>
    </div>
  </div>
</template>

<style scoped>
.legal-page {
  min-height: 100vh;
  background: var(--platform-bg, #f5f6fa);
  color: var(--platform-text, #333);
  display: flex;
  flex-direction: column;
  align-items: center;
}

.legal-page__header {
  width: 100%;
  max-width: 860px;
  padding: 32px 20px 0;
  display: flex;
  align-items: center;
  gap: 16px;
}

.legal-page__back {
  appearance: none;
  border: none;
  padding: 6px 14px;
  background: var(--platform-card-bg, #fff);
  border-radius: 8px;
  font-size: 14px;
  color: var(--platform-accent, #4f6ef7);
  cursor: pointer;
  flex-shrink: 0;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  transition: background 0.2s;
}

.legal-page__back:hover {
  background: var(--platform-hover-bg, #eef0fb);
}

.legal-page__title {
  font-size: 22px;
  font-weight: 700;
  margin: 0;
  flex: 1;
}

.legal-page__body {
  width: 100%;
  max-width: 860px;
  padding: 24px 20px 60px;
}

.legal-page__body section {
  margin-bottom: 28px;
}

.legal-page__body h2 {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--platform-border, #e8e8ee);
}

.legal-page__body p {
  font-size: 15px;
  line-height: 1.75;
  margin: 0 0 10px;
  color: var(--platform-text-secondary, #555);
}

.legal-page__body ul,
.legal-page__body ol {
  margin: 0 0 10px;
  padding-left: 22px;
}

.legal-page__body li {
  font-size: 15px;
  line-height: 1.75;
  margin-bottom: 6px;
  color: var(--platform-text-secondary, #555);
}

html[data-theme="dark"] .legal-page {
  background: #1a1a26;
}

html[data-theme="dark"] .legal-page__back {
  background: #262636;
  color: #7c9aff;
}

html[data-theme="dark"] .legal-page__back:hover {
  background: #30304a;
}

html[data-theme="dark"] .legal-page__body section {
  border-color: #2a2a3a;
}
</style>
