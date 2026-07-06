<script setup>
import { NCard, NH1, NH2, NH3, NP, NText, NTable } from "naive-ui";
import { useI18n } from "../composables/useI18n.js";

const { t } = useI18n();
</script>

<template>
  <div class="docs-container">
    <div class="docs-content">
      <NH1>AgentKit — 多智能体架构引擎</NH1>

      <NCard>
        <NH2>概述</NH2>
        <NP>
          AgentKit 是海颐自研的多智能体（Multi-Agent）架构引擎，为「本析智能」平台提供底层的智能体路由、编排、通信与工具执行能力。
          它以 <NText type="info">Protocol 注入</NText> 为核心理念，通过接口抽象实现宿主应用与库逻辑的彻底解耦。
        </NP>
      </NCard>

      <NCard>
        <NH2>核心设计理念</NH2>

        <NH3>1. Protocol 注入</NH3>
        <NP>
          宿主通过 Python Protocol 接口注入 LLM 调用、工具执行、技能调用等依赖，库本身不耦合任何具体的 LLM 提供商或 Web 框架。
        </NP>

        <NH3>2. 七层组件化</NH3>
        <NP>
          AgentKit 分为 7 个独立子包，可按需引入，每个包职责单一：
        </NP>
        <ul class="feature-list">
          <li><NText code>agentkit-route</NText> — 路由类型与模式推断，零依赖</li>
          <li><NText code>agentkit-aip</NText> — AIP 智能体互操作协议，基于 GB/Z 185 标准</li>
          <li><NText code>agentkit-orchestrate</NText> — 多专精任务编排，无 DB/LLM 依赖</li>
          <li><NText code>agentkit-skills</NText> — Skill 插件框架，统一注册与 dispatch</li>
          <li><NText code>agentkit-subagent</NText> — 隔离上下文子 Agent 运行时</li>
          <li><NText code>agentkit-mcp</NText> — MCP JSON-RPC 协议与客户端</li>
          <li><NText code>agentkit-loop</NText> — Loop Engineering 动态 Prompt 组装</li>
        </ul>

        <NH3>3. 零 ORM / 零 DB 依赖</NH3>
        <NP>
          所有业务上下文通过 <NText code>extras</NText> 字典传递，不依赖任何 ORM 或数据库，可嵌入任何 Python 项目。
        </NP>
      </NCard>

      <NCard>
        <NH2>与主流多智能体框架的对比</NH2>

        <NP>
          下表对比了 AgentKit 与当前主流多智能体框架的设计差异，帮助理解 AgentKit 的定位与优势。
        </NP>

        <NTable striped size="small" class="compare-table">
          <thead>
            <tr>
              <th>维度</th>
              <th>AgentKit</th>
              <th>LangGraph (LangChain)</th>
              <th>CrewAI</th>
              <th>AutoGen (Microsoft)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>架构模式</strong></td>
              <td>Protocol 注入 + 七层组件化</td>
              <td>图计算 (StateGraph)</td>
              <td>角色编排 (Agent → Crew)</td>
              <td>对话代理 (AgentChat)</td>
            </tr>
            <tr>
              <td><strong>依赖耦合</strong></td>
              <td>零平台耦合，零 ORM/DB 依赖</td>
              <td>强耦合 LangChain 生态</td>
              <td>依赖 LangChain / 自有 Agent</td>
              <td>依赖 Azure / OpenAI SDK</td>
            </tr>
            <tr>
              <td><strong>路由机制</strong></td>
              <td>纯逻辑路由 + Protocol SignalDetector</td>
              <td>基于图的状态机路由</td>
              <td>基于角色描述的过程路由</td>
              <td>基于 LLM 的对话路由</td>
            </tr>
            <tr>
              <td><strong>通信协议</strong></td>
              <td>基于 GB/Z 185 标准的 AIP 协议</td>
              <td>LangChain 自有消息格式</td>
              <td>内部消息队列</td>
              <td>AgentChat 协议</td>
            </tr>
            <tr>
              <td><strong>子 Agent 隔离</strong></td>
              <td>独立 loop_state 隔离上下文</td>
              <td>共享 StateGraph 状态</td>
              <td>共享上下文</td>
              <td>共享 Conversation</td>
            </tr>
            <tr>
              <td><strong>Skill 框架</strong></td>
              <td>内置 Skill 插件框架 + MCP 桥接</td>
              <td>依赖 LangChain Tool</td>
              <td>依赖 Crew Tool</td>
              <td>依赖 Function Tool</td>
            </tr>
            <tr>
              <td><strong>测试友好度</strong></td>
              <td>纯函数核心，全部可单测</td>
              <td>需 Mock Graph 运行环境</td>
              <td>需启动完整 Crew</td>
              <td>需 Mock Azure/OpenAI</td>
            </tr>
            <tr>
              <td><strong>包粒度</strong></td>
              <td>7 个独立子包，按需安装</td>
              <td>单体 langchain + langgraph</td>
              <td>单体 crewai</td>
              <td>单体 autogen</td>
            </tr>
            <tr>
              <td><strong>Loop Engineering</strong></td>
              <td>观测驱动的动态 Prompt，非静态提示词</td>
              <td>基于图循环的 ReAct</td>
              <td>基于 Process 的 Step</td>
              <td>基于 AgentChat 的 Turn</td>
            </tr>
          </tbody>
        </NTable>
      </NCard>

      <NCard>
        <NH2>AgentKit 的独特优势</NH2>
        <ul class="feature-list">
          <li>
            <strong>渐进式采用</strong> — 7 个子包可独立安装，不需要一次性引入全部能力。
            例如仅需路由功能时可以只安装 <NText code>agentkit-route</NText>（零依赖）。
          </li>
          <li>
            <strong>宿主中立</strong> — 不依赖 FastAPI、SQLAlchemy、Django 等任何 Web 框架或 ORM。
            <NText code>SkillInvocationContext.extras</NText> 承载所有宿主字段。
          </li>
          <li>
            <strong>标准化通信</strong> — 基于 GB/Z 185 标准的 AIP（Agent Interoperability Protocol），
            提供结构化的 handoff 消息与会话总线，确保多智能体协作的可追溯性。
          </li>
          <li>
            <strong>Loop Engineering</strong> — 区别于传统的静态提示词工程，AgentKit 的 Loop Engineering
            通过观测驱动的动态 Prompt 组装，让每一轮交互都携带当前规划、工具执行结果和交付物证据。
          </li>
          <li>
            <strong>Protocol 契约编程</strong> — 所有 I/O 边界通过 Python Protocol 定义（如
            <NText code>SignalDetector</NText>、<NText code>LoopEvidenceProvider</NText>、
            <NText code>McpToolCaller</NText>），宿主只需实现契约即可接入。
          </li>
        </ul>
      </NCard>

      <NCard>
        <NH2>适用场景</NH2>
        <ul class="feature-list">
          <li>需要自己控制 Agent 路由逻辑，不依赖黑盒编排的业务场景</li>
          <li>需要将多智能体能力嵌入已有 Python 项目（Django / FastAPI / Flask / CLI）</li>
          <li>需要 MCP 协议集成外部工具或数据源</li>
          <li>需要精细控制每一轮 LLM 上下文的 Prompt 编排</li>
          <li>需要标准化 AIP 通信协议的行业应用</li>
        </ul>
      </NCard>
    </div>
  </div>
</template>

<style scoped>
.docs-container {
  max-width: 960px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.docs-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.feature-list {
  padding-left: 20px;
  line-height: 1.8;
}

.compare-table {
  margin-top: 8px;
}

.compare-table :deep(th),
.compare-table :deep(td) {
  white-space: nowrap;
  font-size: 13px;
}

.compare-table :deep(td:first-child) {
  font-weight: 500;
  white-space: nowrap;
  min-width: 100px;
}
</style>
