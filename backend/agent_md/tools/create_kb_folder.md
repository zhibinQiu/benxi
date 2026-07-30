---
name: create_kb_folder
---
在指定文档库范围内新建文件夹。

## When to use
- 用户要求新建文档分类/文件夹
- 写入文档前需要先建目标文件夹

## When NOT to use
- 更新已有文件夹（用 update_kb_folder）
- 删除文件夹（用 delete_kb_folder）

## Returns
- 新建文件夹信息（含 folder_id）

## Parameters

### name (required)
文件夹名称。

### scope (required)
所属范围。

### description (optional)
文件夹说明。
