"""知识图谱 FeaturePlugin 注册。

与本体定义（ontology）是独立的功能模块：
- ontology（本体定义）：管理 TBox — 实体类型、关系类型、属性模式、公理
- kg（知识图谱）：管理 ABox — 实体/关系实例、图谱可视化、LLM 抽取
"""

from app.api import kg as kg_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="kg",
        title="知识图谱",
        description="基于本体约束抽取和编辑实体/关系实例，可视化图谱探索与多跳推理",
        icon="cube-outline",
        permission_code="feature.kg",
        permission_name="知识图谱",
        route="/system/kg",
        router=kg_api.router,
        enabled=True,
        category="tools",
        sort_order=22,
        grant_to_roles=("sys_admin", "member"),
    )
)
