function entityBody(entity) {
  return {
    type_id: entity.type_id,
    name: entity.name,
    description: entity.description || "",
  };
}

function relationBody(rel) {
  return {
    relation_type_id: rel.relation_type_id,
    from_entity_id: rel.from_entity_id,
    to_entity_id: rel.to_entity_id,
    description: rel.description || "",
  };
}

export function buildEntityUpdateUndoEntry(entityId, before, after, updateKgEntity) {
  return {
    kind: "entity-update",
    undo: () => updateKgEntity(entityId, before),
    redo: () => updateKgEntity(entityId, after),
  };
}

export function buildEntityCreateUndoEntry(createdId, body, { createKgEntity, deleteKgEntity }) {
  let currentId = createdId;
  return {
    kind: "entity-create",
    undo: () => deleteKgEntity(currentId),
    redo: async () => {
      const created = await createKgEntity(body);
      currentId = created.id;
    },
  };
}

export function buildEntityDeleteUndoEntry(
  entity,
  relations,
  { createKgEntity, createKgRelation, deleteKgEntity },
  { onSelectionChange } = {}
) {
  const snapshot = entityBody(entity);
  const relationSnapshots = (relations || []).map(relationBody);
  const deletedEntityId = String(entity.id);
  let restoredEntityId = deletedEntityId;

  return {
    kind: "entity-delete",
    undo: async () => {
      const created = await createKgEntity(snapshot);
      restoredEntityId = String(created.id);
      for (const rel of relationSnapshots) {
        const fromId =
          String(rel.from_entity_id) === deletedEntityId
            ? restoredEntityId
            : rel.from_entity_id;
        const toId =
          String(rel.to_entity_id) === deletedEntityId
            ? restoredEntityId
            : rel.to_entity_id;
        try {
          await createKgRelation({
            ...rel,
            from_entity_id: fromId,
            to_entity_id: toId,
          });
        } catch {
          /* 关联端点可能已不存在 */
        }
      }
      onSelectionChange?.(restoredEntityId);
    },
    redo: async () => {
      await deleteKgEntity(restoredEntityId);
      onSelectionChange?.(null);
    },
  };
}

export function buildRelationCreateUndoEntry(createdId, body, { createKgRelation, deleteKgRelation }) {
  let currentId = createdId;
  return {
    kind: "relation-create",
    undo: () => deleteKgRelation(currentId),
    redo: async () => {
      const created = await createKgRelation(body);
      currentId = created.id;
    },
  };
}

export function buildRelationDeleteUndoEntry(rel, { createKgRelation, deleteKgRelation }) {
  const payload = relationBody(rel);
  let currentId = rel.id;
  return {
    kind: "relation-delete",
    undo: async () => {
      const created = await createKgRelation(payload);
      currentId = created.id;
    },
    redo: () => deleteKgRelation(currentId),
  };
}

export function buildEntityTypeUpdateUndoEntry(typeId, before, after, updateKgEntityType) {
  return {
    kind: "entity-type-update",
    undo: () => updateKgEntityType(typeId, before),
    redo: () => updateKgEntityType(typeId, after),
  };
}

export function buildRelationTypeUpdateUndoEntry(typeId, before, after, updateKgRelationType) {
  return {
    kind: "relation-type-update",
    undo: () => updateKgRelationType(typeId, before),
    redo: () => updateKgRelationType(typeId, after),
  };
}
