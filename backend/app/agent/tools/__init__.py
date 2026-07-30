"""app.agent.tools: Schema 生成、参数校验、结果压缩。"""

from app.agent.tools.compress import compress_tool_result
from app.agent.tools.schema import (
    build_function_tool_spec,
    compact_tool_parameters_schema,
)
from app.agent.tools.validate import (
    coerce_dict_field,
    coerce_list_field,
    coerce_string_list,
    format_validation_error,
)

__all__ = [
    "build_function_tool_spec",
    "compact_tool_parameters_schema",
    "format_validation_error",
    "compress_tool_result",
    "coerce_dict_field",
    "coerce_list_field",
    "coerce_string_list",
]

from app.agent import __version__  # noqa: F401
