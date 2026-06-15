/** 文档 ACL / 列表行能力判定（与后端 effective caps 一致） */

export function canModifyDocument(caps) {
  return (
    caps?.can_modify === true ||
    caps?.can_edit === true ||
    caps?.can_manage === true
  );
}

export function canDeleteDocument(caps) {
  return canModifyDocument(caps) || caps?.can_delete === true;
}

export function canBatchSelectDocument(row) {
  return canModifyDocument(row) || row?.can_delete === true;
}

export function canViewDocument(caps) {
  return caps?.can_view !== false;
}

export function emptyDocumentAclCaps() {
  return {
    can_grant: false,
    can_deny: false,
    is_owner: false,
    can_view: true,
    can_query: false,
    can_modify: false,
    can_edit: false,
    can_delete: false,
    can_manage: false,
    can_restore: false,
    effective_level: null,
  };
}
