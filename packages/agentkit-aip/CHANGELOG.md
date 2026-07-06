# Changelog

## 4.6.0 (2026-07-06)

- 版本统一至 4.6.0（与 doc-platform 对齐）
- 新增 `__init__.py` 中 `__version__` 暴露
- 完善 README 示例代码与 API 概览
- 新增 `_platform_config.py` 平台配置支持
- 新增 `external_registry.py` 外部智能体登记支持
- ACDL（Agent Capability Description Language）读取支持

## 0.2.0 (2024-07-06)

- 统一子包版本至 0.2.0
- 添加 `project.urls`、LICENSE、py.typed
- 完善 PyPI classifiers

## 0.1.0 (2024-06-01)

- 初始版本
- AIP 消息类型（AipMessage、AipTask、AipCapability 等）
- AID 身份码编解码（build_agent_aid、parse_agent_id_from_aid）
- Handoff 消息构建与解析（HandoffBuilder、build_specialist_handoff_message）
- 会话消息总线（AipSessionBus）
- 多 hop 编排辅助（merge_hop_citations、best_reply_from_hops）
- AIP SK 生成与校验（generate_aip_sk、hash_aip_sk）
