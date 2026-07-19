# Skills 路由目录（调度层只读 · 简约版）

## carbon-qa
- Title: 双碳问答
- Use when: 双碳领域问题：碳价行情、碳交易、碳达峰碳中和政策、CCER、碳排放核算、节能降碳等
- Don't use when: 其他非双碳领域问题、简单常识问答
- Output: 官方源事实底稿（carbon_price / carbon_policy / carbon_data）；新闻资讯返回浏览器 execute 指引，禁止编造实时数据

## free-web-ai
- Title: 免费 AI 工具
- Use when: 需要免费 AI 对话、代码生成、文案、翻译、生图（文字描述）、识图问答等任务，无需付费 API key
- Don't use when: 企业内部知识库检索（用 invoke_context_subagent(kind=search, ...)）、平台 CRUD、纯 OCR 提取（用 ocr feature）
- Output: AI 文本回复 / 图片 / 图片内容描述

## stock-deep-analysis
- Title: AI 深度解读
- Use when: 单只个股的基本面深度分析：财务数据解读、估值评估、行业竞争格局、成长逻辑验证
- Don't use when: 需要多角色辩论（用 stock-roundtable-debate-*）、专业研究（用 stock-roundtable-research-*）、量价诊断（用 stock-volume-price）
- Output: 结构化个股深度分析报告（含公司概览、财务/估值/行业/成长/风险五维分析）

## stock-roundtable-debate-fundamental
- Title: 辩论圆桌 · 基本面
- Use when: 多角色对抗性辩论研究，聚焦基本面（财务/估值/行业格局）：平台信号研究员/基本面研究员/市场定价研究员/风险反方 + 巴菲特/芒格/彼得林奇/索罗斯/霍华德·马克斯等虚构角色
- Don't use when: 短线方向（用 stock-roundtable-debate-shortterm）、无虚构角色（用 stock-roundtable-research-*）、单只个股问答（用 stock-deep-analysis）
- Output: 完整圆桌研究报告（辩论圆桌·基本面）

## stock-roundtable-debate-shortterm
- Title: 辩论圆桌 · 短线
- Use when: 多角色对抗性辩论研究，聚焦短线（量价/资金/情绪）：9 位参与者对抗性辩论，主持人逐轮裁决
- Don't use when: 基本面方向（用 stock-roundtable-debate-fundamental）、无虚构角色（用 stock-roundtable-research-*）、简单量价诊断（用 stock-volume-price）
- Output: 完整圆桌研究报告（辩论圆桌·短线）

## stock-roundtable-research-fundamental
- Title: 专业研究 · 基本面
- Use when: 无需虚构角色的系统性基本面研究：行业分析师/财务分析师/估值分析师/风险分析师协作
- Don't use when: 需要对抗性辩论（用 stock-roundtable-debate-fundamental）、单只个股问答（用 stock-deep-analysis）、短线方向（用 stock-roundtable-research-shortterm）
- Output: 结构化研究报告（专业研究·基本面）

## stock-roundtable-research-shortterm
- Title: 专业研究 · 短线
- Use when: 无需虚构角色的系统性短线研究：技术分析师/资金分析师/情绪分析师/风险分析师协作
- Don't use when: 需要对抗性辩论（用 stock-roundtable-debate-shortterm）、简单量价诊断（用 stock-volume-price）、基本面方向（用 stock-roundtable-research-fundamental）
- Output: 结构化研究报告（专业研究·短线）

## stock-volume-price
- Title: 量价会诊
- Use when: 简单快捷的短线技术面诊断：量价关系、技术指标、K 线形态、趋势结构、风险边界
- Don't use when: 需要深度多角色分析（用 stock-roundtable-debate-shortterm 或 stock-roundtable-research-shortterm）、基本面分析（用 stock-deep-analysis 或 stock-roundtable-*-fundamental）
- Output: 量价会诊报告（四层框架：指标→形态→趋势→决策）