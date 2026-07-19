"""双碳助手服务 — 复用 carbon_service 取数，异步生成报告/策略。"""

from __future__ import annotations

import asyncio
import logging
import secrets
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.carbon_report import CarbonReport

logger = logging.getLogger(__name__)

_REPORT_TASK_QUEUE: dict[uuid.UUID, asyncio.Task] = {}

REPORT_TYPE_LABELS = {
    "market_brief": "碳交易简报",
    "policy_digest": "政策摘要",
    "strategy": "减碳策略",
}


def new_share_token() -> str:
    return secrets.token_urlsafe(24)


def create_report(
    db: Session,
    user_id: uuid.UUID,
    *,
    subject: str,
    report_type: str,
    industry: str = "",
    region: str = "",
    target_year: str = "",
    ai_context: str = "",
) -> CarbonReport:
    report = CarbonReport(
        user_id=user_id,
        subject=(subject or "").strip()[:128],
        report_type=report_type,
        industry=(industry or "").strip()[:64],
        region=(region or "").strip()[:64],
        target_year=(target_year or "").strip()[:16],
        ai_context=(ai_context or "").strip()[:2000],
        status="pending",
        share_token=new_share_token(),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def get_user_reports(
    db: Session,
    user_id: uuid.UUID,
    *,
    report_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[CarbonReport]:
    stmt = select(CarbonReport).where(CarbonReport.user_id == user_id)
    if report_type:
        stmt = stmt.where(CarbonReport.report_type == report_type)
    if status:
        stmt = stmt.where(CarbonReport.status == status)
    stmt = stmt.order_by(CarbonReport.created_at.desc()).offset(offset).limit(limit)
    return list(db.scalars(stmt).all())


def get_report(db: Session, report_id: uuid.UUID) -> CarbonReport | None:
    return db.get(CarbonReport, report_id)


def get_report_by_share_token(db: Session, share_token: str) -> CarbonReport | None:
    token = (share_token or "").strip()
    if not token:
        return None
    return db.scalars(
        select(CarbonReport).where(CarbonReport.share_token == token)
    ).first()


def cancel_report_task(
    db: Session,
    user_id: uuid.UUID,
    report_id: uuid.UUID,
) -> CarbonReport:
    from app.models.job import Job
    from app.services.job_service import cancel_job as cancel_system_job

    report = db.get(CarbonReport, report_id)
    if not report or report.user_id != user_id:
        raise ValueError("报告不存在")
    if report.status in ("completed", "failed", "cancelled"):
        raise ValueError(f"报告状态为「{report.status}」，无法取消")

    report.status = "cancelled"
    db.commit()
    db.refresh(report)

    if report.system_job_id:
        try:
            sys_job = db.get(Job, report.system_job_id)
            if sys_job:
                cancel_system_job(db, sys_job, reason="双碳报告任务已取消")
        except (ValueError, ImportError):
            pass

    task = _REPORT_TASK_QUEUE.pop(report_id, None)
    if task and not task.done():
        task.cancel()
    return report


def delete_report(db: Session, user_id: uuid.UUID, report_id: uuid.UUID) -> None:
    report = db.get(CarbonReport, report_id)
    if not report or report.user_id != user_id:
        raise ValueError("报告不存在")
    if report.status in ("pending", "running"):
        raise ValueError("进行中的任务请先取消")
    db.delete(report)
    db.commit()


def report_title(report: CarbonReport) -> str:
    label = REPORT_TYPE_LABELS.get(report.report_type, report.report_type)
    return f"「{report.subject}」{label}"


def _update_progress(db: Session, report: CarbonReport, progress: int, msg: str) -> None:
    report.progress = progress
    report.error_message = msg
    db.commit()
    if report.system_job_id:
        from app.services.job_service import update_job_status

        try:
            update_job_status(db, report.system_job_id, "running", progress=progress)
        except ValueError:
            pass


async def _collect_facts(report: CarbonReport) -> str:
    """复用 carbon_service 官方源取数，组装事实底稿。"""
    from app.services import carbon_service as carbon

    subject = report.subject
    parts: list[str] = []

    if report.report_type == "market_brief":
        price = await carbon.fetch_carbon_price(keyword=subject)
        parts.append("### 碳价行情\n\n" + str(price.get("summary_md") or "本次未获取到"))
        data = await carbon.fetch_carbon_data("ccer", keyword=subject)
        parts.append("### CCER / 市场数据\n\n" + str(data.get("summary_md") or "本次未获取到"))
        intl = await carbon.fetch_carbon_data("international", keyword=subject)
        parts.append("### 国际碳市场\n\n" + str(intl.get("summary_md") or "本次未获取到"))
    elif report.report_type == "policy_digest":
        policy = await carbon.fetch_carbon_policy(keyword=subject)
        parts.append("### 政策法规\n\n" + str(policy.get("summary_md") or "本次未获取到"))
        local = await carbon.fetch_carbon_data(
            "local", keyword=report.region or subject
        )
        parts.append("### 地方方案\n\n" + str(local.get("summary_md") or "本次未获取到"))
    else:  # strategy
        kw = " ".join(
            x for x in (subject, report.industry, report.region) if x
        ).strip() or subject
        policy = await carbon.fetch_carbon_policy(keyword=kw)
        parts.append("### 相关政策\n\n" + str(policy.get("summary_md") or "本次未获取到"))
        emission = await carbon.fetch_carbon_data("emission", keyword=kw)
        parts.append("### 排放与核算\n\n" + str(emission.get("summary_md") or "本次未获取到"))
        local = await carbon.fetch_carbon_data("local", keyword=report.region or kw)
        parts.append("### 地方双碳路径\n\n" + str(local.get("summary_md") or "本次未获取到"))

    return "\n\n".join(parts)


def _system_prompt(report: CarbonReport) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    label = REPORT_TYPE_LABELS.get(report.report_type, "双碳报告")
    base = (
        f"你是双碳领域专业顾问，正在出具「{report.subject}」的{label}。\n"
        f"生成时间：{now}\n"
        "硬约束：仅基于事实底稿；缺口写「本次未获取到」；禁止编造碳价、政策条文或减排数字；"
        "注明可核验来源 URL（若底稿中有）。\n\n"
    )
    if report.report_type == "market_brief":
        return base + (
            "请按以下 Markdown 标题输出：\n"
            f"# 「{report.subject}」碳交易简报\n\n"
            "## 先看结论\n"
            "## 一、碳价与成交概况\n"
            "## 二、CCER 与配额动态\n"
            "## 三、国际市场对照\n"
            "## 四、风险与跟踪点\n"
            "## 五、研究边界\n"
        )
    if report.report_type == "policy_digest":
        return base + (
            "请按以下 Markdown 标题输出：\n"
            f"# 「{report.subject}」双碳政策摘要\n\n"
            "## 先看结论\n"
            "## 一、顶层与部委政策要点\n"
            "## 二、地方与行业落地\n"
            "## 三、对企业的影响与合规提示\n"
            "## 四、跟踪清单\n"
            "## 五、研究边界\n"
        )
    industry = report.industry or "（未指定行业）"
    region = report.region or "全国"
    year = report.target_year or "2030"
    return base + (
        f"行业：{industry}；地区：{region}；目标年：{year}\n"
        "请按以下 Markdown 标题输出：\n"
        f"# 「{report.subject}」减碳策略建议\n\n"
        "## 先看结论\n"
        "## 一、现状与政策约束\n"
        "## 二、减排路径选项（技术/管理/市场）\n"
        "## 三、分阶段行动建议\n"
        "## 四、成本与风险提示\n"
        "## 五、验证与跟踪清单\n"
        "## 六、研究边界\n"
        "不构成投资或合规承诺；策略建议需结合企业实测数据复核。\n"
    )


async def _synthesize_report(report: CarbonReport, facts: str) -> str:
    from app.integrations.deepseek_client import chat_completion_message_async

    context_note = ""
    if report.ai_context:
        context_note = f"\n## 用户补充\n\n{report.ai_context}\n"

    choice = await chat_completion_message_async(
        messages=[
            {"role": "system", "content": _system_prompt(report)},
            {
                "role": "user",
                "content": (
                    f"## 事实底稿（来自官方源工具）\n\n{facts[:14000]}\n"
                    f"{context_note}\n"
                    "请基于以上底稿出具完整报告。"
                ),
            },
        ],
        temperature=0.4,
        timeout=240,
    )
    if choice:
        text = str((choice.get("message") or {}).get("content") or "").strip()
        if text:
            return text
    label = REPORT_TYPE_LABELS.get(report.report_type, "双碳报告")
    return (
        f"# 「{report.subject}」{label}\n\n"
        "## 先看结论\n\n本次未能生成分析正文，以下为事实底稿摘要。\n\n"
        f"{facts[:8000]}"
    )


async def _run_report_task(report_id: uuid.UUID) -> None:
    from app.database import SessionLocal
    from app.services.notification_service import create_notification

    db = SessionLocal()
    try:
        report = db.get(CarbonReport, report_id)
        if not report or report.status == "cancelled":
            return
        report.status = "running"
        report.progress = 10
        db.commit()

        if report.system_job_id:
            from app.services.job_service import update_job_status

            try:
                update_job_status(db, report.system_job_id, "running", progress=10)
            except ValueError:
                pass

        _update_progress(db, report, 25, "正在从官方源获取双碳数据...")
        facts = await _collect_facts(report)

        _update_progress(db, report, 55, "正在撰写报告...")
        content = await _synthesize_report(report, facts)

        report = db.get(CarbonReport, report_id)
        if not report or report.status == "cancelled":
            return

        report.content = content
        report.status = "completed"
        report.progress = 100
        report.error_message = "报告已生成"
        report.completed_at = datetime.now()
        db.commit()

        if report.system_job_id:
            from app.services.job_service import update_job_status

            try:
                update_job_status(db, report.system_job_id, "done", progress=100)
            except ValueError:
                pass

        label = REPORT_TYPE_LABELS.get(report.report_type, "双碳报告")
        create_notification(
            db,
            user_id=report.user_id,
            title=f"{report.subject} {label} 已生成",
            body=f"「{report.subject}」的{label}已完成，可前往查看。",
            link="/system/carbon-assistant",
        )
    except asyncio.CancelledError:
        logger.info("carbon report task cancelled: %s", report_id)
        raise
    except Exception as exc:
        logger.exception("carbon report task failed: %s", exc)
        try:
            report = db.get(CarbonReport, report_id)
            if report and report.status != "cancelled":
                report.status = "failed"
                report.error_message = str(exc)[:500]
                db.commit()
                if report.system_job_id:
                    from app.services.job_service import update_job_status

                    try:
                        update_job_status(
                            db,
                            report.system_job_id,
                            "failed",
                            progress=0,
                            error_message=str(exc)[:200],
                        )
                    except ValueError:
                        pass
                create_notification(
                    db,
                    user_id=report.user_id,
                    title=f"{report.subject} 报告生成失败",
                    body=str(exc)[:200],
                    link="/system/carbon-assistant",
                )
        except Exception:
            pass
    finally:
        db.close()
        _REPORT_TASK_QUEUE.pop(report_id, None)


async def submit_report_task(report: CarbonReport) -> None:
    from app.database import SessionLocal
    from app.services.job_service import create_job

    db = SessionLocal()
    try:
        system_job = create_job(
            db,
            job_type="carbon_report",
            created_by=report.user_id,
            payload={
                "report_id": str(report.id),
                "subject": report.subject,
                "report_type": report.report_type,
            },
        )
        db_report = db.get(CarbonReport, report.id)
        if db_report:
            db_report.system_job_id = system_job.id
        db.commit()
    finally:
        db.close()

    task = asyncio.create_task(_run_report_task(report.id))
    _REPORT_TASK_QUEUE[report.id] = task


async def trading_snapshot(*, keyword: str = "") -> dict[str, Any]:
    """碳交易看板：并行拉碳价 + CCER + 政策要点。"""
    from app.services import carbon_service as carbon

    kw = (keyword or "").strip() or "全国碳市场"
    price, ccer, policy = await asyncio.gather(
        carbon.fetch_carbon_price(keyword=kw),
        carbon.fetch_carbon_data("ccer", keyword=kw),
        carbon.fetch_carbon_policy(keyword=kw),
    )
    return {
        "keyword": kw,
        "price": price,
        "ccer": ccer,
        "policy": policy,
    }
