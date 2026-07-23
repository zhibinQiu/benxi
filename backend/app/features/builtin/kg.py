"""知识图谱 — 兼容壳（已并入「本体定义」）。

不再作为独立菜单/功能清单项；``/api/v1/kg`` 由 ontology 插件挂载。
保留 ``feature.kg`` 权限码供旧授权兼容别名检查。
"""

from app.features.base import FeaturePlugin
from app.features.registry import register

register(
    FeaturePlugin(
        id="kg",
        title="知识图谱",
        description="已并入「本体定义」实例层（兼容保留）",
        icon="cube-outline",
        permission_code="feature.kg",
        permission_name="知识图谱（兼容）",
        route=None,
        router=None,
        enabled=False,
        show_in_catalog=False,
        category="tools",
        sort_order=22,
        grant_to_roles=(),
        tag="已并入本体定义",
    )
)
