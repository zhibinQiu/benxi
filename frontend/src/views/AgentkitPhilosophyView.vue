<script setup>
import { ref, nextTick, onMounted, onUnmounted, watch } from "vue";
import { useRouter } from "vue-router";
import { NIcon } from "naive-ui";
import { ArrowBackOutline } from "@vicons/ionicons5";
import { mountMermaidInElement, unmountMermaidInElement } from "../utils/mermaidRender.js";

const router = useRouter();
const pageRef = ref(null);
const scrolling = ref(false);

function mountMermaid() {
  nextTick(() => {
    if (pageRef.value) {
      mountMermaidInElement(pageRef.value);
    }
  });
}

let scrollTimer = null;
function onPageScroll() {
  if (!scrolling.value) { scrolling.value = true; }
  clearTimeout(scrollTimer);
  scrollTimer = setTimeout(() => { scrolling.value = false; }, 140);
}

onMounted(() => {
  mountMermaid();
  pageRef.value?.addEventListener("scroll", onPageScroll, { passive: true });
});
onUnmounted(() => {
  if (pageRef.value) unmountMermaidInElement(pageRef.value);
  pageRef.value?.removeEventListener("scroll", onPageScroll);
  clearTimeout(scrollTimer);
});
watch(() => pageRef.value, mountMermaid);
</script>

<template>
  <div
    ref="pageRef"
    class="philosophy-page"
    :class="{ 'philosophy-page--scrolling': scrolling }"
  >
    <!-- Header -->
    <header class="philosophy-header">
      <div class="philosophy-header__inner">
        <button
          type="button"
          class="philosophy-header__chip philosophy-header__chip--back"
          @click="router.back()"
        >
          <n-icon :size="17" :component="ArrowBackOutline" />
          <span>返回</span>
        </button>

        <span class="philosophy-header__title">AgentKit 设计哲学</span>

        <div class="philosophy-header__spacer" />
      </div>
    </header>

    <!-- Hero -->
    <div class="philosophy-hero">
      <h1 class="philosophy-hero__title">我的智能体设计哲学</h1>
      <p class="philosophy-hero__sub">让 AI 真正干活的工程法则 —— AgentKit 的设计理念与实践</p>
    </div>

    <div class="philosophy-content">
      <!-- ================== 一、开篇 ================== -->
      <section class="philosophy-chapter">
        <h2 class="philosophy-chapter-title">一、开篇：智能体的"灵魂"是什么？</h2>
        <p>2024 年以来，几乎每个月都有新的 AI 智能体框架冒出来。每个人都在说"我的智能体如何如何"，但很少有人认真思考一个问题：<strong>智能体和聊天机器人到底有什么区别？</strong></p>
        <p>聊天机器人是"一问一答"：你问它答，它说完就结束。但智能体不同。一个真正的智能体，核心能力是<strong>自主完成多步骤任务</strong>——它要自己规划、自己行动、自己观察结果、自己决定下一步做什么，而不是等着人类每一步都告诉它该干嘛。</p>

        <div class="md-mermaid-wrap">
          <pre class="md-mermaid">
flowchart LR
  A[👤 用户提问] --> B{这是谁？}
  B -->|聊天机器人| C[💬 一次性回答]
  C --> D[🏁 结束]
  B -->|智能体| E[🧠 理解目标]
  E --> F[📋 制定计划]
  F --> G[🔧 执行工具]
  G --> H[👀 观察结果]
  H --> I{任务完成？}
  I -->|否| F
  I -->|是| J[📝 输出成果]
  J --> K[🏁 结束]</pre>
        </div>

        <p>我花了三个多月的时间，从零构建了一个叫 <strong>AgentKit</strong> 的智能体框架。它不是那种塞满炫技功能的"玩具"，而是一套经过真实业务检验的工程实践。这篇文章就是想把这些设计思路说清楚，让不懂技术的普通读者也能理解：<strong>一个靠谱的智能体，到底是怎么被"设计"出来的</strong>。</p>
      </section>

      <!-- ================== 二、奥卡姆剃刀 ================== -->
      <section class="philosophy-chapter">
        <h2 class="philosophy-chapter-title">二、奥卡姆剃刀：最好的功能就是没有功能</h2>

        <div class="md-mermaid-wrap">
          <pre class="md-mermaid">
flowchart TD
  A[📝 收到需求] --> B{加新功能？}
  B -->|用户明确需要| C[✅ 实现]
  B -->|"以后可能有用"| D[❌ 不做]
  C --> E{有重复代码？}
  E -->|有| F[♻️ 提取复用]
  E -->|没有| G[✅ 保持简洁]
  D --> H[记录观察]
  H --> I{需求确认出现？}
  I -->|是| C
  I -->|否| J[🗑️ 删掉]

  style D fill:#f66,color:#fff
  style C fill:#6c6,color:#fff
  style G fill:#6c6,color:#fff</pre>
        </div>

        <p>我的哲学第一条，来自一把 14 世纪的剃刀。奥卡姆的威廉说："如无必要，勿增实体。"翻译成大白话就是——<strong>不要把简单的事情搞复杂</strong>。</p>
        <p>很多智能体框架的通病是：什么都想做。你可以在 system prompt 里塞五十条指令，给它注册一百个工具，它看起来无所不能，实际上什么都干不好。就像一个人身上装了二十把瑞士军刀，最后连拧螺丝都找不对工具。</p>
        <p>AgentKit 的设计原则非常明确：</p>
        <ul>
          <li><strong>不做不存在的功能。</strong> 用户没说要的，就不做。不要为了"以后可能有用"去提前堆砌抽象层。</li>
          <li><strong>不做无用的抽象。</strong> 一个工具函数就是一段代码，不需要经过三层工厂模式才能调用。</li>
          <li><strong>能复用就复用。</strong> 写代码最忌讳的事情之一就是"重复造轮子"——同样的工具调用逻辑，不要在三个地方各写一遍。</li>
        </ul>
        <p>打个比方：造一辆车，车轮就是圆的，没必要把它设计成八边形再通过算法转成圆形。<strong>框架的核心价值是解决问题，不是展示你有多会设计模式。</strong></p>
      </section>

      <!-- ================== 三、循环工程 ================== -->
      <section class="philosophy-chapter">
        <h2 class="philosophy-chapter-title">三、循环工程：智能体是"跑"出来的，不是"想"出来的</h2>
        <p>很多人对智能体的理解还停留在"我给它一段指令，它输出一段结果"。但这本质上跟普通的大模型对话没有区别。真正让智能体变得"智能"的，是一个叫做 <strong>循环</strong> 的东西。</p>
        <p>AgentKit 提出了一个 <strong>"六相循环"</strong> 模型，每一步都不复杂，但组合起来就很强大：</p>

        <div class="md-mermaid-wrap">
          <pre class="md-mermaid">
flowchart TB
  subgraph 循环体
    A[1️⃣ 输入捕获] --> B[2️⃣ 上下文组装]
    B --> C[3️⃣ 模型推理]
    C --> D[4️⃣ 动作执行]
    D --> E[5️⃣ 观测校验]
    E --> F[6️⃣ 记忆更新]
    F -->|"继续"| A
  end
  E -->|"任务完成"| G[📝 输出结果]
  G --> H[🏁 结束]

  style A fill:#4a9eff,color:#fff
  style B fill:#4a9eff,color:#fff
  style C fill:#4a9eff,color:#fff
  style D fill:#4a9eff,color:#fff
  style E fill:#4a9eff,color:#fff
  style F fill:#4a9eff,color:#fff</pre>
        </div>

        <p>你发现没有？这其实跟人类做事的逻辑一模一样。你要完成一件事，先看看自己有什么信息（上下文），想一下该做什么（推理），动手干（动作），看看效果（观测），记下来（记忆），不行就再来一轮。</p>
        <p>传统做法的误区是：<strong>把所有的指令全部塞进 system prompt 里。</strong> 那就像考试前通宵背书，考场上全忘了。AgentKit 的做法恰恰相反：<strong>system prompt 越短越好，只放"循环契约"——告诉智能体你该用什么方式工作。</strong> 真正的任务目标、规划步骤、工具观测结果，都在每一轮动态组装进 user message 里。这就像一个人带队干活：你不必在早上就把全天的每一句话都交代清楚，而是在每个阶段告诉他："目前的情况是这样，你接下来做这件事。"</p>
      </section>

      <!-- ================== 四、工具 ================== -->
      <section class="philosophy-chapter">
        <h2 class="philosophy-chapter-title">四、工具是肌肉，智能体用它来"动手"</h2>
        <p>如果你把 LLM 比作大脑，那么工具（Tool）就是它的手和脚。没有工具的智能体，只能纸上谈兵。</p>

        <div class="md-mermaid-wrap">
          <pre class="md-mermaid">
flowchart LR
  subgraph LLM大脑
    A[🧠 LLM 推理]
  end
  subgraph 工具系统
    B[🔧 输入参数] --> C[⚡ 执行动作]
    C --> D[📦 返回结果]
    D --> E[🔍 压缩摘要]
    E --> F[🔑 生成指纹]
    F --> G[💾 缓存结果]
  end
  A -->|"决定调用"| B
  G -->|"相同指纹直接返回"| A
  E -->|"新结果"| A

  style A fill:#9b59b6,color:#fff
  style B fill:#3498db,color:#fff
  style C fill:#2ecc71,color:#fff
  style D fill:#2ecc71,color:#fff
  style E fill:#f39c12,color:#fff
  style F fill:#e74c3c,color:#fff
  style G fill:#e74c3c,color:#fff</pre>
        </div>

        <p>AgentKit 的工具系统有几个关键设计：</p>
        <p><strong>第一，每个工具的结果都要"压缩"。</strong> LLM 的上下文窗口是有限的。有些工具（比如网页搜索）返回的结果可能有一本书那么厚。如果不加处理直接扔给模型，大脑很快就塞满了。所以我们会对工具结果做"精加工"：summary + 关键数据 + 计数，把几万字的原始输出压缩成几百字的重点摘要。这就像秘书在老板开会前先准备好一页纸的简报，而不是把原始文件全部摊在他桌上。</p>
        <p><strong>第二，相同的工具调用不做第二次。</strong> 你有没有遇到过这种情况：问智能体一个问题，它明明已经查过数据库了，过了一会儿又问了一遍同样的问题？这不是它笨，而是它"忘了"自己做过什么。AgentKit 用了一个叫 <strong>工具指纹</strong> 的技术。每次调用工具，我们都会根据"工具名 + 参数"生成一个唯一的 SHA256 指纹。下一次如果遇到完全相同的调用，直接从缓存里取结果，不走第二遍。这既省了时间，也省了钱（API 调用是要花钱的）。</p>
        <p><strong>第三，工具系统是轻量级的。</strong> AgentKit 的 MCP（Model Context Protocol）客户端只有不到 200 行代码。它不做复杂的会话管理，不做花哨的负载均衡，就做一件事：连上外部工具服务器，调用工具，返回结果。</p>
      </section>

      <!-- ================== 五、四个基础概念 ================== -->
      <section class="philosophy-chapter">
        <h2 class="philosophy-chapter-title">五、四个基础概念：为什么缺一不可</h2>
        <p>在 AgentKit 里，所有的智能体能力都建立在四个基础概念之上：<strong>工具（Tool）</strong>、<strong>技能（Skill）</strong>、<strong>子智能体（Sub-agent）</strong> 和 <strong>专精智能体（Specialist Agent）</strong>。它们不是随便分出来的，而是每一层解决一个特定的问题。少了任何一个，系统的能力就会出现断层。</p>

        <div class="md-mermaid-wrap">
          <pre class="md-mermaid">
flowchart TB
  subgraph 专精智能体层[Specialist Agent · 各司其职]
    S1[research<br/>资料检索]
    S2[report<br/>报告撰写]
    S3[platform<br/>系统管理]
    S4[skill-dev<br/>技能开发]
  end
  subgraph 子智能体层[Sub-agent · 隔离并行]
    C1[侦察兵 A]:::child
    C2[侦察兵 B]:::child
    C3[侦察兵 C]:::child
  end
  subgraph 技能层[Skill · 肌肉记忆]
    K1[knowledge_report<br/>知识报告技能]
    K2[data_query<br/>数据查询技能]
    K3[auto_reply<br/>自动回复技能]
  end
  subgraph 工具层[Tool · 手和脚]
    T1[🔧 web_search]
    T2[🔧 db_query]
    T3[🔧 send_email]
    T4[🔧 file_read]
  end
  K1 --> T1 & T2
  K2 --> T2
  K3 --> T3 & T4
  S1 --> K1
  S2 --> K2
  S3 --> K3
  C1 --> T1
  C2 --> T2
  C3 --> T3

  classDef child fill:#9b59b6,color:#fff</pre>
        </div>

        <h3>1. 工具（Tool）—— 智能体的"手和脚"</h3>
        <p>工具是最小单位的可执行动作。一个工具就是"输入参数 → 执行动作 → 返回结果"这么一个简单的闭环。比如 <code>web_search("北京天气")</code> → 返回搜索结果。<strong>为什么不能没有工具？</strong> 因为 LLM 本身是"只说不做"的。它再聪明，也发不了邮件、查不了数据库、访问不了网页。工具就是给 LLM 安装的"外挂器官"——没有它，智能体只能侃侃而谈，什么实事都干不了。</p>

        <h3>2. 技能（Skill）—— 可复用的"肌肉记忆"</h3>
        <p>如果说 Tool 是单一动作，那 Skill 就是<strong>一套编排好的动作组合</strong>，再加上元数据（什么时候该用、什么时候不该用、输出什么格式）。<strong>为什么不能没有 Skill？</strong> 因为 LLM 没有"肌肉记忆"。每次遇到同一类任务，它都要从头推理一遍"该调用哪个工具、按什么顺序"。这不仅慢、费钱，还容易出错。Skill 就是把这些"已验证有效的执行路径"固化下来，像人类的肌肉记忆一样——下次遇到同样的情况，不用过脑子，直接上手干。</p>
        <p>而且 Skill 还有一个更厉害的能力：<strong>可以在运行时动态创建</strong>。如果一个智能体反复做不好某类任务，调度会触发"技能开发"流程——先调研问题的本质，然后编写一个 Skill 脚本并注册到系统中。下次遇到同样的问题，直接调用这个新 Skill 就行，不用再让 LLM 从零推理。这是 AgentKit 的<strong>自进化能力</strong>。</p>

        <h3>3. 子智能体（Sub-agent）—— 派出去的"侦察兵"</h3>
        <p>子智能体本质上是一个<strong>临时创建、独立运行、用完即走</strong>的迷你智能体。父智能体（通常是调度器）给子智能体一个明确的子任务，然后它带着这个任务和一套受限的工具集，进入一个"隔离沙箱"开始工作。工作完成后，它把结果浓缩成一段摘要"汇报"给父智能体，然后自己就消失了。<strong>为什么不能没有子智能体？</strong> 第一是<strong>隔离</strong>——多个任务不会互相干扰；第二是<strong>并行</strong>——多个子任务可以同时跑；第三是<strong>预算控制</strong>——每个子智能体的产出被压缩成摘要后才回传，不撑爆父智能体的上下文。</p>

        <h3>4. 专精智能体（Specialist Agent）—— 各司其职的"部门经理"</h3>
        <p>一个智能体不可能什么都会。专精智能体的思路很简单：<strong>为不同的领域配备不同的智能体，每个只做自己最擅长的事。</strong> 目前系统中常见的专精角色包括：research（资料检索）、platform（系统管理）、report（报告撰写）、diagram（图示绘制）、rpa（浏览器自动化）、scheduler（定时任务）、skill-dev（技能开发）等。<strong>为什么不能没有专精智能体？</strong> 因为没有分工就没有效率。一个什么都能干的通用智能体，在每一个细分领域都会被专精智能体完爆。</p>

        <div class="philosophy-callout">
          <p><strong>用真实流程串起来理解：</strong> 用户说"帮我调研 AI 编程工具的趋势，写一份报告，发到群里"。调度器（Orchestrator）先分析需求，派一个<strong>子智能体</strong>去执行调研，这个子智能体在隔离环境里调用 <code>web_search</code> <strong>工具</strong>上网搜索；子智能体返回摘要后，调度器把摘要转交给 <strong>report 专精智能体</strong>；report 专精智能体调用一个叫 <code>trend_report</code> 的 <strong>Skill</strong>，自动生成报告；最后调度器调用 <code>send_message</code> 工具把报告发到群里。工具负责动手、技能固化经验、子智能体隔离并行、专精智能体聚焦领域。缺了任何一个，这个流程要么跑不动，要么跑不好，要么跑不快。</p>
        </div>
      </section>

      <!-- ================== 六、路由与编排 ================== -->
      <section class="philosophy-chapter">
        <h2 class="philosophy-chapter-title">六、路由与编排：让专业的人做专业的事</h2>
        <p>（上一节已经详细解释了四个概念及其关系，这一节聚焦"它们是怎么被串起来的"。）</p>

        <div class="md-mermaid-wrap">
          <pre class="md-mermaid">
flowchart TB
  U[👤 用户需求] --> O[🎯 调度智能体<br/>Orchestrator]
  O --> R{路由模式}
  R -->|串行| A1[research<br/>专精智能体]
  A1 -->|步骤1 结果| A2[report<br/>专精智能体]
  R -->|并行| B1[research<br/>专精智能体]
  R -->|并行| B2[platform<br/>专精智能体]
  R -->|并行| B3[report<br/>专精智能体]
  R -->|协助| C1[platform<br/>专精智能体]
  C1 -.->|发起协助请求| C2[research<br/>专精智能体]
  A2 --> Merge[📋 汇总结果]
  B1 & B2 & B3 --> Merge
  C1 --> Merge
  Merge --> Out[📝 最终输出]

  style O fill:#e74c3c,color:#fff
  style Merge fill:#9b59b6,color:#fff</pre>
        </div>

        <p>AgentKit 采用了一种叫做 <strong>"星型编排"</strong> 的架构。核心思想是：有一个<strong>调度智能体</strong>（Orchestrator）负责理解用户需求，然后把它拆成子任务，分发给<strong>专精智能体</strong>去执行。就像一个大厨接到订单一桌菜，他不会自己去切所有的菜，而是告诉配菜师傅、面点师傅、烧烤师傅各自干什么，最后把所有人做好的东西拼成一桌菜。</p>

        <p>这里面有三个关键模式：</p>
        <ul>
          <li><strong>串行</strong> —— 任务有明确的先后顺序。比如先搜索资料，再写报告。前面的步骤是后面的前提。</li>
          <li><strong>并行</strong> —— 任务之间互不依赖。比如同时查三个不同网站的资料，同时跑，最后汇总。</li>
          <li><strong>协助（Assist）</strong> —— 一个专精智能体干到一半发现需要另一个领域的知识，主动请求调度安排"外援"。这就像财务做报表时发现需要了解某个业务部门的流程，就请业务同事来帮忙。</li>
        </ul>
        <p>还有一个很重要的设计叫 <strong>"能力升级"</strong>。如果一个专精智能体反复做不好某件事，调度不会一直让它重试，而是会触发"技能开发"流程——先调研，再写一个可复用的 Skill 固化下来。下次遇到同样的问题，直接调用脚本就行了，不用再让 LLM 从头推理。</p>
      </section>

      <!-- ================== 七、预算意识 ================== -->
      <section class="philosophy-chapter">
        <h2 class="philosophy-chapter-title">七、预算意识：智能体的"能量守恒"</h2>

        <div class="md-mermaid-wrap">
          <pre class="md-mermaid">
flowchart TD
  A[原始输入] --> B{超出预算？}
  B -->|"对话历史超长"| C[✂️ 历史裁剪]
  B -->|"工具结果过大"| D[📦 工具压缩]
  B -->|"并发任务过多"| E[🔗 路由上限]
  B -->|"检索材料超标"| F[📐 上下文预算]
  C & D & E & F --> G[✅ 符合预算]
  G --> H[🧠 LLM 推理]

  style C fill:#e74c3c,color:#fff
  style D fill:#e74c3c,color:#fff
  style E fill:#e74c3c,color:#fff
  style F fill:#e74c3c,color:#fff
  style G fill:#2ecc71,color:#fff</pre>
        </div>

        <p>这是几乎所有智能体框架都忽视的问题，但在我看来可能是最重要的。LLM 的上下文窗口是有上限的，API 调用是按 token 算钱的。如果你不控制开销，一个稍微复杂一点的任务就能花掉几十美元。AgentKit 把"预算控制"作为一等设计原则：</p>
        <ul>
          <li><strong>历史裁剪</strong> —— 对话长了不是全留着，而是从最近的开始保留，同时约束条数和字符数。旧的聊天记录会被"遗忘"。</li>
          <li><strong>工具压缩</strong> —— 超大的工具输出会被自动压缩，图片二进制数据会被直接丢弃，只保留摘要。</li>
          <li><strong>路由上限</strong> —— 一个任务最多串行 3 次 handoff，并行最多 2 个智能体同时跑。不是不能更多，而是不值得——边际效益递减。</li>
          <li><strong>上下文预算</strong> —— 每条消息的字符数、每个检索块的大小都有上限，超过就截断。</li>
        </ul>
        <p>听上去好像有点"抠门"？但这就是工程思维的体现：<strong>资源是有限的，好的设计不是能处理无限资源的情况，而是在有限资源下做到最好。</strong></p>
      </section>

      <!-- ================== 八、人机协作 ================== -->
      <section class="philosophy-chapter">
        <h2 class="philosophy-chapter-title">八、人机协作：智能体知道什么时候该问人</h2>

        <div class="md-mermaid-wrap">
          <pre class="md-mermaid">
sequenceDiagram
  participant U as 👤 用户
  participant A as 🤖 智能体
  participant S as 📦 响应盒
  A->>A: 遇到关键决策点
  A->>S: 1. 创建请求盒
  S-->>U: 2. 前端展示
  U->>S: 3. 用户选择
  S-->>A: 4. 读取响应
  A->>A: 5. 根据结果继续
  A->>U: 输出最终结果</pre>
        </div>

        <p>我见过很多智能体设计，它们最大的毛病是：<strong>自作主张</strong>。用户说"帮我处理一下这些文档"，好家伙，它二话不说就把一百份文档全删了。AgentKit 引入了 <strong>HITL（Human-in-the-Loop，人在回路）</strong> 机制。核心是"响应盒"模式：智能体遇到需要人类确认的事情→创建一个"请求盒"→前端展示给用户→用户选择→智能体读取结果后继续执行。这个机制解决了一个根本性的信任问题：<strong>用户不需要时刻盯着智能体，但关键环节必须由人拍板。</strong></p>
      </section>

      <!-- ================== 九、上下文管理 ================== -->
      <section class="philosophy-chapter">
        <h2 class="philosophy-chapter-title">九、上下文管理：智能体的"记忆法"</h2>

        <div class="md-mermaid-wrap">
          <pre class="md-mermaid">
flowchart TB
  subgraph 短期记忆[短期记忆 · 本轮完整内容]
    M1[🗣️ 当前对话]
    M2[🔧 刚调用的工具结果]
    M3[📋 正在执行的计划]
  end
  subgraph 中期记忆[中期记忆 · 历史简报]
    M4[📄 前几轮要点摘要]
    M5[🔍 追问检测关联]
  end
  subgraph 长期记忆[长期记忆 · 固化的经验]
    M6[💾 Skill 技能库]
    M7[🏷️ 网站结构缓存]
    M8[📌 常用查询模板]
  end
  M1 & M2 --->|对话轮次结束| M4
  M4 --->|反复验证有效| M6
  M5 --->|提炼模式| M7
  M7 --> M8

  classDef short fill:#4a9eff,color:#fff
  classDef mid fill:#f39c12,color:#fff
  classDef long fill:#2ecc71,color:#fff
  class M1,M2,M3 short
  class M4,M5 mid
  class M6,M7,M8 long</pre>
        </div>

        <p>智能体不能什么都记，但同样不能什么都忘。AgentKit 的上下文管理策略像人脑一样分层次：<strong>短期记忆</strong>保留本轮对话的完整信息；<strong>中期记忆</strong>保留前几轮对话的"简报"——不保留原文，只保留要点；<strong>长期记忆</strong>则存放从经验中提炼的结论，比如调研过的网站结构、常用的查询模板，这些会被写成 Skill 固化下来。</p>
        <p>AgentKit 还有一个非常有特色的设计叫 <strong>"追问检测"</strong>。用户说"继续"、"然后呢"、"另外也查一下"，这些不是全新的独立问题，而是对前文的跟进。系统会识别出这些"跟帖"，把它们和前面的对话关联起来处理，而不是当成一个全新的对话轮次。这听起来很自然，但很多 AI 产品其实做不到这一点——你刚问完"北京有什么好玩的"，说了一句"还有呢"，它可能就忘了上一个话题，开始答非所问。</p>
      </section>

      <!-- ================== 十、结语 ================== -->
      <section class="philosophy-chapter philosophy-chapter--epilogue">
        <h2 class="philosophy-chapter-title">十、结语：智能体不是魔法，是工程</h2>
        <p><strong>智能体不是靠大模型"涌现"出来的，而是靠工程一点点搭起来的。</strong> 很多人以为，有了 GPT-4 这样的强大模型，智能体就是"往里面加 prompt 就行"。这种想法就像以为有了最好的发动机，就能直接开上马路一样天真。一辆好车需要发动机，但还需要轮胎、方向盘、刹车、安全带、仪表盘、悬挂系统……每一个部件都不起眼，但少了任何一个，车都开不远。</p>
        <p>AgentKit 的设计哲学归结起来就是下面 10 条：</p>
        <ol class="philosophy-principles">
          <li><strong>别做多余的事</strong> —— 奥卡姆剃刀，不加不必要的功能</li>
          <li><strong>让它跑起来</strong> —— 循环工程，智能体是在迭代中变聪明的</li>
          <li><strong>给它好用的工具</strong> —— 但要压缩结果、避免重复调用</li>
          <li><strong>把经验固化下来</strong> —— Skill 让已验证的执行路径可复用</li>
          <li><strong>隔离并行，用完即焚</strong> —— 子智能体解决"多路探索"问题</li>
          <li><strong>让专业的人做专业的事</strong> —— 专精智能体各司其职</li>
          <li><strong>分而治之</strong> —— 路由与编排把复杂任务拆解成可管理的单元</li>
          <li><strong>控制预算</strong> —— 好的设计知道资源有限</li>
          <li><strong>关键时刻问人</strong> —— 不要让智能体自作主张</li>
          <li><strong>学会记和忘</strong> —— 上下文管理是智能体的记忆术</li>
        </ol>
        <p>没有一条是高深的理论，每一条都是我在实际编码和调试中踩过的坑。把这些坑填平了，智能体才能真正帮你干活。</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.philosophy-page {
  position: relative;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overscroll-behavior-y: contain;
  -webkit-overflow-scrolling: touch;
  background: #fff;
  font-family: "Inter", ui-sans-serif, -apple-system, BlinkMacSystemFont,
    "Segoe UI", "PingFang SC", "Helvetica Neue", "Microsoft YaHei", sans-serif;
}

html[data-theme="dark"] .philosophy-page {
  background: #0f0f16;
}

/* ========== Header ========== */
.philosophy-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  height: 43px;
  box-sizing: border-box;
  background: transparent;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  transition: background 0.25s ease, backdrop-filter 0.25s ease;
}

.philosophy-page--scrolling .philosophy-header {
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

html[data-theme="dark"] .philosophy-page--scrolling .philosophy-header {
  background: rgba(15, 15, 22, 0.82);
  border-bottom-color: #2a2a36;
}

.philosophy-header__inner {
  width: 100%;
  height: 100%;
  margin: 0;
  padding: 0 max(10px, env(safe-area-inset-right, 0px)) 0 max(10px, env(safe-area-inset-left, 0px));
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.philosophy-header__chip {
  appearance: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  box-sizing: border-box;
  height: 30px;
  padding: 0 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  font-size: 14px;
  font-weight: 500;
  color: #555;
  cursor: pointer;
  transition: color 0.18s ease, background 0.18s ease;
}

.philosophy-header__chip:hover {
  color: #000;
  background: rgba(0, 0, 0, 0.05);
}

html[data-theme="dark"] .philosophy-header__chip {
  color: #999;
}

html[data-theme="dark"] .philosophy-header__chip:hover {
  color: #e0e0e8;
  background: rgba(255, 255, 255, 0.08);
}

.philosophy-header__chip--back {
  font-size: 13px;
  flex-shrink: 0;
}

.philosophy-header__title {
  font-size: 14px;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 0 1 auto;
  opacity: 0;
  transition: opacity 0.25s ease;
}

.philosophy-page--scrolling .philosophy-header__title {
  opacity: 1;
}

html[data-theme="dark"] .philosophy-header__title {
  color: #ccc;
}

.philosophy-header__spacer {
  flex: 0 0 70px;
}

@media (max-width: 480px) {
  .philosophy-header__spacer {
    flex: 0 0 10px;
  }
  .philosophy-header__chip--back span {
    display: none;
  }
}

/* ========== Hero ========== */
.philosophy-hero {
  padding: 80px 29px 48px;
  text-align: center;
}

.philosophy-hero__title {
  margin: 0 0 8px;
  font-size: clamp(1.6rem, 3.2vw, 2.2rem);
  font-weight: 700;
  letter-spacing: -0.03em;
  background: linear-gradient(135deg, #4a9eff, #9b59b6);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

html[data-theme="dark"] .philosophy-hero__title {
  background: linear-gradient(135deg, #6ab0ff, #b07cd8);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.philosophy-hero__sub {
  margin: 0;
  font-size: clamp(14px, 1.2vw, 16px);
  color: #777;
}

html[data-theme="dark"] .philosophy-hero__sub {
  color: #999;
}

/* ========== Content ========== */
.philosophy-content {
  padding: 0 20px 64px;
  max-width: 960px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.philosophy-chapter {
  padding: 32px;
  border-radius: 16px;
  background: #f8f9fc;
  border: 1px solid #e8eaef;
}

html[data-theme="dark"] .philosophy-chapter {
  background: #171720;
  border-color: #282836;
}

.philosophy-chapter-title {
  margin: 0 0 16px;
  font-size: clamp(1.15rem, 1.8vw, 1.35rem);
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #111;
}

html[data-theme="dark"] .philosophy-chapter-title {
  color: #e0e0e8;
}

.philosophy-chapter h3 {
  margin: 20px 0 8px;
  font-size: 1.05rem;
  font-weight: 600;
  color: #222;
}

html[data-theme="dark"] .philosophy-chapter h3 {
  color: #ccc;
}

.philosophy-chapter p {
  margin: 0 0 12px;
  font-size: clamp(15px, 1.15vw, 16px);
  line-height: 1.75;
}

html[data-theme="dark"] .philosophy-chapter p {
  color: #c0c0cc;
}

.philosophy-chapter ul,
.philosophy-chapter ol {
  margin: 0 0 12px;
  padding-left: 22px;
  font-size: clamp(15px, 1.15vw, 16px);
  line-height: 1.8;
}

html[data-theme="dark"] .philosophy-chapter ul,
html[data-theme="dark"] .philosophy-chapter ol {
  color: #c0c0cc;
}

.philosophy-chapter li {
  margin-bottom: 4px;
}

.philosophy-chapter code {
  padding: 2px 6px;
  border-radius: 4px;
  background: #e8eaef;
  font-size: 0.9em;
  color: #e74c3c;
}

html[data-theme="dark"] .philosophy-chapter code {
  background: #282836;
  color: #ff6b6b;
}

/* ── Mermaid ── */
:deep(.md-mermaid-wrap) {
  margin: 20px 0;
  padding: 16px;
  border-radius: 12px;
  background: #fff;
  border: 1px solid #e0e2e8;
  overflow-x: auto;
}

html[data-theme="dark"] :deep(.md-mermaid-wrap) {
  background: #1e1e2a;
  border-color: #333344;
}

:deep(.md-mermaid) {
  margin: 0;
  white-space: pre-wrap;
  font-size: 13px;
  color: #666;
}

html[data-theme="dark"] :deep(.md-mermaid) {
  color: #aaa;
}

:deep(.md-mermaid--loading) {
  opacity: 0.5;
}

:deep(.md-mermaid-svg) {
  display: flex;
  justify-content: center;
}

:deep(.md-mermaid-svg svg) {
  max-width: 100%;
  height: auto;
}

/* ── Callout ── */
.philosophy-callout {
  margin-top: 16px;
  padding: 16px 20px;
  border-radius: 10px;
  background: linear-gradient(135deg, color-mix(in srgb, #4a9eff 8%, transparent), color-mix(in srgb, #9b59b6 8%, transparent));
  border-left: 4px solid #4a9eff;
}

html[data-theme="dark"] .philosophy-callout {
  background: linear-gradient(135deg, color-mix(in srgb, #4a9eff 12%, #171720), color-mix(in srgb, #9b59b6 12%, #171720));
  border-left-color: #6ab0ff;
}

.philosophy-callout p {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
}

html[data-theme="dark"] .philosophy-callout p {
  color: #c0c0cc;
}

/* ── Principles list ── */
.philosophy-principles {
  counter-reset: principle;
  list-style: none;
  padding: 0 !important;
}

.philosophy-principles li {
  counter-increment: principle;
  padding: 6px 0 6px 36px;
  position: relative;
  border-bottom: 1px solid #e8eaef;
}

html[data-theme="dark"] .philosophy-principles li {
  border-bottom-color: #282836;
}

.philosophy-principles li:last-child {
  border-bottom: none;
}

.philosophy-principles li::before {
  content: counter(principle);
  position: absolute;
  left: 0;
  top: 6px;
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: linear-gradient(135deg, #4a9eff, #9b59b6);
  color: #fff;
  font-size: 12px;
}

/* ── Epilogue ── */
.philosophy-chapter--epilogue {
  background: linear-gradient(135deg, color-mix(in srgb, #4a9eff 6%, #f8f9fc), color-mix(in srgb, #9b59b6 6%, #f8f9fc));
}

html[data-theme="dark"] .philosophy-chapter--epilogue {
  background: linear-gradient(135deg, color-mix(in srgb, #4a9eff 8%, #171720), color-mix(in srgb, #9b59b6 8%, #171720));
}

/* ── Responsive ── */
@media (max-width: 720px) {
  .philosophy-content {
    padding: 0 14px 48px;
  }

  .philosophy-hero {
    padding: 70px 18px 36px;
  }

  .philosophy-chapter {
    padding: 20px;
  }

  :deep(.md-mermaid-wrap) {
    padding: 10px;
    margin: 14px 0;
  }
}

@media (max-width: 480px) {
  .philosophy-hero {
    padding: 64px 14px 28px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .philosophy-header {
    background: rgba(255, 255, 255, 0.82) !important;
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
    border-bottom: 1px solid rgba(0, 0, 0, 0.06) !important;
  }
  html[data-theme="dark"] .philosophy-header {
    background: rgba(15, 15, 22, 0.82) !important;
    border-bottom-color: #2a2a36 !important;
  }
}
</style>
