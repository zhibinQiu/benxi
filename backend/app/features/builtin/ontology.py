"""本体定义 FeaturePlugin 注册。

产品层统一为「本体定义」：模式层（TBox）+ 实例图谱（ABox）。
REST 仍分 ``/ontology/*`` 与 ``/kg/*``，由本插件一并挂载。
"""

from fastapi import APIRouter

from app.api import kg as kg_api
from app.api import ontology as ontology_api
from app.features.base import FeaturePlugin
from app.features.registry import register

_router = APIRouter()
_router.include_router(ontology_api.router)
_router.include_router(kg_api.router)

register(
    FeaturePlugin(
        id="ontology",
        title="本体定义",
        description="定义实体/关系类型与公理（模式层），并管理实体实例、图谱探索与 LLM 抽取（实例层）",
        icon="git-network",
        permission_code="feature.ontology",
        permission_name="本体定义",
        route="/system/ontology",
        router=_router,
        enabled=True,
        category="tools",
        sort_order=21,
        grant_to_roles=("sys_admin", "member"),
    )
)
