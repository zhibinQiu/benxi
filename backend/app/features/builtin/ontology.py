"""本体定义 FeaturePlugin 注册。

与知识图谱（kg）是独立的功能模块：
- ontology（本体定义）：管理 TBox — 实体类型、关系类型、属性模式、公理
- kg（知识图谱）：管理 ABox — 实体/关系实例、图谱可视化、LLM 抽取
"""

from app.api import ontology as ontology_api
from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="ontology",
        title="本体定义",
        description="定义实体类型、关系类型、属性模式与推理公理，构建领域语义层",
        icon="git-network",
        permission_code="feature.ontology",
        permission_name="本体定义",
        route="/system/ontology",
        router=ontology_api.router,
        enabled=True,
        category="tools",
        sort_order=21,
        grant_to_roles=("sys_admin", "member"),
    )
)
