---
name: update_department
---
更新部门名称或父级（需管理员权限）。

## When to use
- 重命名部门或调整组织挂载

## When NOT to use
- 新建/删除部门

## Returns
- 更新后的部门信息

## Parameters

### department_id / department_name (optional)
定位部门。

### name (optional)
新名称。

### parent_id / parent_name (optional)
新父部门。

### clear_parent (optional)
为 true 时清除父级（升为顶级）。
