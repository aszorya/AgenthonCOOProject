"""Format COOPilot workflow output for Telegram."""

from __future__ import annotations

import re

from backend.orchestrator import WorkflowRun


def escape_md(text: str) -> str:
    """Escape Telegram MarkdownV1 special chars in user/LLM content."""
    return re.sub(r"([_*\[\]`])", r"\\\1", str(text))


def format_feed_line(entry: dict[str, str]) -> str:
    status = entry.get("status", "ok")
    msg = entry.get("message", "")
    icon = {"ok": "✅", "blocked": "⛔", "error": "❌", "skipped": "⏭️"}.get(status, "▶️")
    return f"{icon} {escape_md(msg)}"


def format_workflow_summary(run: WorkflowRun) -> str:
    lines = [
        f"*{escape_md(run.workflow.replace('_', ' ').title())}* — status: `{run.status}`",
        "",
    ]
    ctx = run.context

    if ctx.get("orchestrator_plan"):
        lines += ["*Roadmap*", escape_md(str(ctx["orchestrator_plan"])[:1500]), ""]
    if ctx.get("plan"):
        lines += ["*Strategy*", escape_md(str(ctx["plan"])[:1200]), ""]
    if ctx.get("operations_tasks"):
        lines += ["*Tasks*", escape_md(str(ctx["operations_tasks"])[:1200]), ""]
    if ctx.get("payment_url"):
        lines += ["*DOKU Payment*", ctx["payment_url"], ""]
    if ctx.get("confirmation_message"):
        lines += ["*Pesan konfirmasi*", escape_md(str(ctx["confirmation_message"])[:1500])]
    if ctx.get("telegram_invoice_sent"):
        lines += ["", "*Telegram invoice:* terkirim ke vendor ✅"]
    elif ctx.get("telegram_id"):
        lines += ["", "_Telegram invoice: belum terkirim (vendor perlu /start bot)_"]
    if ctx.get("memory_note"):
        lines += ["", f"_{escape_md(str(ctx['memory_note']))}_"]
    if ctx.get("supply_needs"):
        names = ", ".join(
            str(s.get("name", s)) if isinstance(s, dict) else str(s)
            for s in ctx["supply_needs"][:8]
        )
        lines += ["", f"*Supply:* {escape_md(names)}"]
    if ctx.get("discovered_vendors"):
        vnames = ", ".join(v.get("name", "") for v in ctx["discovered_vendors"][:6])
        lines += ["", f"*Vendor:* {escape_md(vnames)}"]
    if ctx.get("outreach_log"):
        lines += ["", f"*Outreach:* {len(ctx['outreach_log'])} vendor dihubungi"]
    if ctx.get("telegram_reorder_notified"):
        lines += ["", "*Notifikasi reorder:* terkirim ke Telegram ✅"]

    return "\n".join(lines)
