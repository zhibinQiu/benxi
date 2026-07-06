"""业务域模块（Facade + 应用服务），供 API 层与 features 调用。

各子包对应 bounded context，避免 services/ 与 integrations/ 交叉引用失控。
"""
