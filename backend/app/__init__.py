"""Document AI platform — control plane (single enterprise).

分层（依赖单向：平台 → 可抽离库）：
- 可抽离库：``app.agent``（智能体运行时）、``app.semantic``（语义决策）
- 接入：``app.api``
- 编排/业务：``app.services``
- 平台能力：``app.tools``、``app.skills``、``app.features``
- 适配/基建：``app.core``、``app.ontology``、``app.models``、``app.schemas``、``app.config``、``app.storage``
"""

__version__ = "4.9.0"
