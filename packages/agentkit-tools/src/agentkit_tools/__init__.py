"""agentkit-tools: 工具注册、Schema 生成、参数校验、结果压缩。"""

from agentkit_tools.compress import compress_tool_result
from agentkit_tools.registry import ToolRegistry, ToolDef
from agentkit_tools.schema import (
    build_function_tool_spec,
    compact_tool_parameters_schema,
)
from agentkit_tools.validate import (
    format_validation_error,
    validate_tool_arguments,
)

__all__ = [
    "ToolRegistry",
    "ToolDef",
    "build_function_tool_spec",
    "compact_tool_parameters_schema",
    "validate_tool_arguments",
    "format_validation_error",
    "compress_tool_result",
]

__version__ = "4.6.0"
