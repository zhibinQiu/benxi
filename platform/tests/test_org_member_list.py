"""部门成员清单 — 路由与确定性回复（禁止 LLM 编造）。"""

from app.services.agent_intent import needs_knowledge_retrieval
from app.services.agent_skill_router import (
    is_org_member_list_question,
    is_platform_system_data_message,
)


def test_org_member_list_question_detects_dept_people_query():
    assert is_org_member_list_question("咨询服务部有哪些人")
    assert is_org_member_list_question("技术部有谁")
    assert not is_org_member_list_question("碳配额政策有哪些要点")


def test_platform_system_data_includes_dept_member_query():
    assert is_platform_system_data_message("咨询服务部有哪些人")


def test_dept_member_query_skips_doc_retrieval():
    assert needs_knowledge_retrieval("咨询服务部有哪些人") is False


def test_format_department_members_reply_from_kg():
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models.kg import KgEntity, KgEntityType, KgRelation, KgRelationType
    from app.models.org import Department, User
    from app.services.kg_service import (
        ensure_ontology_defaults,
        format_department_members_reply,
        list_kg_department_members,
    )

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == "admin"))
        assert user is not None
        ensure_ontology_defaults(db)
        dept = db.scalar(select(Department).where(Department.name == "咨询服务部"))
        if dept is None:
            dept = Department(name="咨询服务部", sort_order=999)
            db.add(dept)
            db.flush()

        org_type = db.scalar(select(KgEntityType).where(KgEntityType.code == "org"))
        person_type = db.scalar(select(KgEntityType).where(KgEntityType.code == "person"))
        employs = db.scalar(select(KgRelationType).where(KgRelationType.code == "employs"))
        org_ent = db.scalar(
            select(KgEntity).where(
                KgEntity.owner_id == user.id,
                KgEntity.name == "咨询服务部",
            )
        )
        if org_ent is None:
            org_ent = KgEntity(
                type_id=org_type.id,
                name="咨询服务部",
                description="组织部门",
                owner_id=user.id,
                created_by=user.id,
                scope="company",
            )
            db.add(org_ent)
            db.flush()
        person_ent = db.scalar(
            select(KgEntity).where(
                KgEntity.owner_id == user.id,
                KgEntity.name == "测试用户A",
            )
        )
        if person_ent is None:
            person_ent = KgEntity(
                type_id=person_type.id,
                name="测试用户A",
                description="手机 13800000001",
                owner_id=user.id,
                created_by=user.id,
                scope="company",
            )
            db.add(person_ent)
            db.flush()
        exists = db.scalar(
            select(KgRelation.id).where(
                KgRelation.owner_id == user.id,
                KgRelation.from_entity_id == org_ent.id,
                KgRelation.to_entity_id == person_ent.id,
            )
        )
        if not exists:
            db.add(
                KgRelation(
                    relation_type_id=employs.id,
                    from_entity_id=org_ent.id,
                    to_entity_id=person_ent.id,
                    owner_id=user.id,
                    created_by=user.id,
                )
            )
        db.commit()

        members = list_kg_department_members(db, user, "咨询服务部")
        assert any(name == "测试用户A" for name, _ in members)

        reply = format_department_members_reply(db, user, "咨询服务部有哪些人")
        assert reply
        assert "测试用户A" in reply
        assert "张伟" not in reply
        assert "本体图谱" in reply
    finally:
        db.close()
