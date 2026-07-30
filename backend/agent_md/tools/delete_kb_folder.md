---
name: delete_kb_folder
---
删除文档库文件夹。破坏性操作，必须 confirm=true。

## When to use
- 用户明确要求删除某文件夹，并已确认

## When NOT to use
- 仅清空或移动其中文档（先处理文档再用本工具）
- 未确认时

## Returns
- 删除结果

## Parameters

### confirm (required)
必须为 true。

### scope (optional)
默认 personal。

### folder_id / folder_name (optional)
定位目标文件夹。
