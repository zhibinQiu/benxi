---
name: delete_department
---
删除部门。破坏性操作，须 confirm=true（需管理员权限）。

## When to use
- 管理员明确要求删除某部门并已确认

## When NOT to use
- 仅改名或改挂载（用 update_department）
- 部门下仍有未处理用户/子部门时需先处理

## Returns
- 删除结果

## Parameters

### confirm (required)
必须为 true。

### department_id / department_name (optional)
定位部门。
