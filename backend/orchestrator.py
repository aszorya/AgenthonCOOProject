from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.agents.communication_agent import CommunicationAgent
from backend.agents.finance_agent import FinanceAgent
from backend.agents.inventory_agent import InventoryAgent
from backend.agents.memory_agent import MemoryAgent
from backend.agents.operations_agent import OperationsAgent
from backend.agents.payment_agent import PaymentAgent
from backend.agents.reorder_agent import ReorderAgent
from backend.agents.sales_inventory_agent import SalesInventoryAgent
from backend.agents.strategy_agent import StrategyAgent
from backend.agents.supply_analysis_agent import SupplyAnalysisAgent
from backend.agents.vendor_discovery_agent import VendorDiscoveryAgent
from backend.agents.vendor_outreach_agent import VendorOutreachAgent
from backend.business_profile import load_profile
from backend import reorder_notifications, sales_service
from backend.agents.base_agent import AgentResult
from backend.business_profile import build_business_context, is_profile_complete
from backend.config import ModelRole
from backend.intent_router import UserIntent
from backend import sumopod_client
from backend.supplier_matching import filter_supplies_without_manual
from backend.supplier_registry import find_supplier, list_suppliers


@dataclass
class WorkflowRun:
    workflow: str
    user_goal: str
    steps: list[AgentResult] = field(default_factory=list)
    feed: list[dict[str, str]] = field(default_factory=list)
    status: str = "running"
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow,
            "user_goal": self.user_goal,
            "status": self.status,
            "feed": self.feed,
            "steps": [s.__dict__ for s in self.steps],
            "context": {k: v for k, v in self.context.items() if k != "memories"},
        }


def _append_step(run: WorkflowRun, result: AgentResult) -> None:
    run.steps.append(result)
    label = result.agent.replace("_", " ").title()
    run.feed.append(
        {
            "agent": result.agent,
            "status": result.status,
            "message": f"[{label}] {result.message}",
        }
    )
    if result.data:
        run.context.update(result.data)


def _operations_planning(context: dict[str, Any]) -> AgentResult:
    goal = context.get("user_goal", "")
    biz = context.get("business_context", "")
    vendors = context.get("registered_suppliers") or list_suppliers(context.get("chat_id", ""))
    sup_line = ", ".join(s.get("name", "") for s in vendors) or "belum ada"
    prompt = f"""Goal: {goal}
Business: {biz}
Vendor terdaftar: {sup_line}

Buat task list operasional (max 5 item). Jangan mengarang nama pihak baru."""
    try:
        tasks = sumopod_client.chat(
            prompt,
            system="COOPilot Operations Agent. Facts only.",
            role=ModelRole.SUB_AGENT,
        )
        return AgentResult("operations_plan", "ok", "Operations plan generated", {"operations_tasks": tasks})
    except Exception as e:
        return AgentResult("operations_plan", "error", str(e), {})


def orchestrate_plan(user_goal: str, business_context: str = "") -> str:
    prompt = f"""Business goal: {user_goal}
Context: {business_context}

Buat rencana operasional (max 5 bullet). Jangan mengarang nama vendor."""
    return sumopod_client.chat(
        prompt,
        system="COOPilot Orchestrator. Use only provided context.",
        role=ModelRole.ORCHESTRATOR,
    )


def run_supply_chain_flow(context: dict[str, Any]) -> WorkflowRun:
    """Onboarding agent: analisis supply → cari vendor → outreach → inventory."""
    goal = context.get("user_goal", "Setup rantai pasok otomatis")
    profile = context.get("profile")
    run = WorkflowRun(workflow="supply_chain", user_goal=goal, context=dict(context))

    if not is_profile_complete(profile):
        _append_step(
            run,
            AgentResult(
                "system",
                "blocked",
                "Profil belum lengkap. Selesaikan /setup (nama bisnis, jenis usaha, modal, lokasi).",
                {},
            ),
        )
        run.status = "blocked"
        return run

    ctx = {**context, "business_context": build_business_context(profile), "user_goal": goal}
    try:
        ctx["budget_available"] = float(str(profile.get("budget", "0")).replace(".", "").replace(",", ""))
    except (TypeError, ValueError):
        ctx["budget_available"] = 0

    for agent_cls in (SupplyAnalysisAgent, VendorDiscoveryAgent, VendorOutreachAgent, InventoryAgent):
        result = agent_cls().run(ctx)
        _append_step(run, result)
        if result.status in ("blocked", "error"):
            run.status = result.status
            run.context = ctx
            return run
        ctx.update(result.data)

    run.status = "ok"
    run.context = ctx
    return run


def run_find_supplier_flow(context: dict[str, Any]) -> WorkflowRun:
    """
    Discovery hanya untuk bahan yang belum punya supplier manual (/tambah_supplier).
    """
    goal = context.get("user_goal", "Cari supplier untuk bahan belum terdaftar")
    profile = context.get("profile")
    chat_id = context.get("chat_id")
    run = WorkflowRun(workflow="find_supplier", user_goal=goal, context=dict(context))

    if not is_profile_complete(profile):
        _append_step(
            run,
            AgentResult("system", "blocked", "Profil belum lengkap. /setup dulu.", {}),
        )
        run.status = "blocked"
        return run

    ctx = {**context, "business_context": build_business_context(profile), "user_goal": goal}
    try:
        ctx["budget_available"] = float(str(profile.get("budget", "0")).replace(".", "").replace(",", ""))
    except (TypeError, ValueError):
        ctx["budget_available"] = 0

    registered = list_suppliers(chat_id) if chat_id else []
    ctx["registered_suppliers"] = registered

    supply = SupplyAnalysisAgent().run(ctx)
    _append_step(run, supply)
    if supply.status in ("blocked", "error"):
        run.status = supply.status
        run.context = ctx
        return run
    ctx.update(supply.data)

    all_needs = ctx.get("supply_needs") or []
    missing, covered = filter_supplies_without_manual(all_needs, registered)

    covered_names = ", ".join(c.get("name", "") for c in covered) or "-"
    _append_step(
        run,
        AgentResult(
            "system",
            "ok",
            f"{len(covered)} bahan sudah punya supplier manual (dilewati): {covered_names}",
            {"supplies_skipped_manual": covered, "supplies_to_discover": missing},
        ),
    )

    if not missing:
        _append_step(
            run,
            AgentResult(
                "system",
                "ok",
                "Semua bahan inti sudah punya supplier manual. Tidak perlu discovery.",
                {},
            ),
        )
        run.status = "ok"
        run.context = ctx
        return run

    ctx["supply_needs"] = missing
    missing_names = ", ".join(m.get("name", "") for m in missing)
    _append_step(
        run,
        AgentResult(
            "system",
            "ok",
            f"Mencari vendor untuk {len(missing)} bahan: {missing_names}",
            {},
        ),
    )

    for agent_cls in (VendorDiscoveryAgent, VendorOutreachAgent):
        result = agent_cls().run(ctx)
        _append_step(run, result)
        if result.status in ("blocked", "error"):
            run.status = result.status
            run.context = ctx
            return run
        ctx.update(result.data)

    inv = InventoryAgent().run(ctx)
    _append_step(run, inv)

    run.status = "ok"
    run.context = ctx
    return run


def _notify_reorder(
    run: WorkflowRun,
    ctx: dict[str, Any],
    *,
    trigger_source: str,
) -> None:
    reorder_items = ctx.get("reorder_items") or []
    if not reorder_items:
        return
    profile = ctx.get("profile") or {}
    vendor = ctx.get("selected_supplier") or {}
    note = reorder_notifications.send_reorder_notification(
        ctx.get("chat_id"),
        business_name=profile.get("business_name", "Bisnis"),
        reorder_items=reorder_items,
        reorder_orders=ctx.get("reorder_orders"),
        vendor_name=vendor.get("name") or ctx.get("vendor_name", ""),
        payment_url=str(ctx.get("payment_url") or ""),
        payment_amount=int(ctx.get("payment_amount") or 0),
        trigger_source=trigger_source,
        last_sale=ctx.get("last_sale"),
    )
    _append_step(run, note)
    ctx["telegram_reorder_notified"] = note.status == "ok"


def run_cashier_sale_flow(context: dict[str, Any]) -> WorkflowRun:
    """
  Pipeline kasir: catat penjualan → kurangi stok bahan baku → reorder jika stok rendah.
    """
    goal = context.get("user_goal", "Penjualan kasir")
    run = WorkflowRun(workflow="cashier_sale", user_goal=goal, context=dict(context))
    chat_id = context.get("chat_id")
    profile = context.get("profile") or (load_profile(chat_id) if chat_id else None)

    if not chat_id:
        _append_step(run, AgentResult("system", "blocked", "chat_id bisnis wajib", {}))
        run.status = "blocked"
        return run

    product = (context.get("product") or "").strip()
    qty = int(context.get("qty") or 1)
    if not product:
        _append_step(run, AgentResult("system", "blocked", "Nama produk wajib", {}))
        run.status = "blocked"
        return run

    sale = sales_service.record_sale(
        chat_id,
        product=product,
        qty=qty,
        cashier_name=str(context.get("cashier_name") or "kasir"),
        unit_price=float(context.get("unit_price") or 0),
    )
    _append_step(run, AgentResult("cashier", "ok", f"Penjualan tercatat: {qty}x {product}", {"last_sale": sale}))

    ctx = {
        **context,
        "profile": profile,
        "last_sale": sale,
        "chat_id": chat_id,
        "business_context": build_business_context(profile),
    }
    try:
        ctx["budget_available"] = float(str((profile or {}).get("budget", "0")).replace(".", "").replace(",", ""))
    except (TypeError, ValueError):
        ctx["budget_available"] = 0

    sales_inv = SalesInventoryAgent().run(ctx)
    _append_step(run, sales_inv)
    if sales_inv.status == "error":
        run.status = "error"
        run.context = ctx
        return run
    ctx.update(sales_inv.data)

    reorder = ReorderAgent().run(ctx)
    _append_step(run, reorder)
    ctx.update(reorder.data)

    reorder_items = ctx.get("reorder_items") or []
    if reorder_items and not ctx.get("selected_supplier"):
        _notify_reorder(run, ctx, trigger_source="Dashboard kasir (belum ada vendor)")
        _append_step(
            run,
            AgentResult(
                "system",
                "blocked",
                "Reorder terpicu tetapi belum ada vendor. Jalankan /mulai di Telegram.",
                {},
            ),
        )
        run.status = "blocked"
        run.context = ctx
        return run

    if reorder_items and ctx.get("selected_supplier"):
        for agent_cls in (FinanceAgent, PaymentAgent, CommunicationAgent, OperationsAgent):
            result = agent_cls().run(ctx)
            _append_step(run, result)
            if result.status in ("blocked", "error"):
                _notify_reorder(run, ctx, trigger_source="Dashboard kasir (pembayaran gagal)")
                run.status = result.status
                run.context = ctx
                return run
            ctx.update(result.data)

        from backend import inventory_service

        for item_row in reorder_items[:3]:
            item = item_row.get("item", "")
            if item:
                restocked = int(item_row.get("initial_qty") or 100)
                inventory_service.update_stock(chat_id, item, restocked)

        _append_step(
            run,
            AgentResult(
                "reorder",
                "ok",
                f"Pemesanan ulang diproses untuk {len(reorder_items)} bahan",
                {},
            ),
        )
        _notify_reorder(run, ctx, trigger_source="Dashboard kasir")

    run.status = "ok"
    run.context = ctx
    return run


def run_auto_reorder_flow(context: dict[str, Any]) -> WorkflowRun:
    """Cek stok rendah → trigger pembayaran ke vendor terkait jika ada."""
    goal = context.get("user_goal", "Auto-reorder stok habis")
    run = WorkflowRun(workflow="auto_reorder", user_goal=goal, context=dict(context))
    chat_id = context.get("chat_id")
    profile = context.get("profile") or (load_profile(chat_id) if chat_id else None)
    ctx = {**context, "profile": profile, "chat_id": chat_id}

    reorder = ReorderAgent().run(ctx)
    _append_step(run, reorder)
    if reorder.status != "ok":
        run.status = reorder.status
        run.context = ctx
        return run

    reorder_items = ctx.get("reorder_items") or []
    if not reorder_items:
        run.status = "ok"
        run.context = ctx
        return run

    if not ctx.get("selected_supplier"):
        _notify_reorder(run, ctx, trigger_source="Perintah /reorder (belum ada vendor)")
        _append_step(
            run,
            AgentResult("system", "blocked", "Belum ada vendor. Jalankan /mulai untuk discovery.", {}),
        )
        run.status = "blocked"
        run.context = ctx
        return run

    try:
        ctx["budget_available"] = float(str((profile or {}).get("budget", "0")).replace(".", "").replace(",", ""))
    except (TypeError, ValueError):
        ctx["budget_available"] = 0

    for agent_cls in (FinanceAgent, PaymentAgent, CommunicationAgent, OperationsAgent):
        result = agent_cls().run(ctx)
        _append_step(run, result)
        if result.status in ("blocked", "error"):
            _notify_reorder(run, ctx, trigger_source="Perintah /reorder (pembayaran gagal)")
            run.status = result.status
            run.context = ctx
            return run
        ctx.update(result.data)

    from backend import inventory_service

    for item_row in reorder_items[:3]:
        item = item_row.get("item", "")
        if item:
            restocked = int(item_row.get("initial_qty") or 100)
            inventory_service.update_stock(chat_id, item, restocked)

    _notify_reorder(run, ctx, trigger_source="Perintah /reorder")

    run.status = "ok"
    run.context = ctx
    return run


def run_goal_flow(context: dict[str, Any], intent: UserIntent) -> WorkflowRun:
    goal = context.get("user_goal", "")
    profile = context.get("profile")
    if not is_profile_complete(profile):
        run = WorkflowRun(workflow=intent.value, user_goal=goal)
        _append_step(
            run,
            AgentResult(
                "system",
                "blocked",
                "Profil belum lengkap. Lengkapi via /setup (nama bisnis, jenis usaha, modal, lokasi).",
                {},
            ),
        )
        run.status = "blocked"
        return run

    if intent == UserIntent.SUPPLY_CHAIN:
        return run_supply_chain_flow(context)

    biz = build_business_context(profile)
    run = WorkflowRun(workflow=intent.value, user_goal=goal, context=dict(context))
    ctx = {**context, "business_context": biz, "user_goal": goal}

    try:
        ctx["budget_available"] = float(
            str(profile.get("budget", profile.get("modal", "0"))).replace(".", "").replace(",", "")
        )
    except (TypeError, ValueError):
        ctx["budget_available"] = 0

    strategy = StrategyAgent().run(ctx)
    _append_step(run, strategy)
    if strategy.status == "error":
        run.status = "error"
        return run
    ctx.update(strategy.data)

    memory = MemoryAgent().run(ctx)
    _append_step(run, memory)
    if memory.status in ("blocked", "error"):
        run.status = memory.status
        return run
    ctx.update(memory.data)

    try:
        plan_text = orchestrate_plan(goal, biz)
        _append_step(run, AgentResult("orchestrator", "ok", "Roadmap created", {"plan": plan_text}))
        ctx["orchestrator_plan"] = plan_text
    except Exception as e:
        _append_step(run, AgentResult("orchestrator", "error", str(e), {}))

    ops = _operations_planning(ctx)
    _append_step(run, ops)
    ctx.update(ops.data)

    if intent == UserIntent.VENDOR_PAYMENT:
        if not ctx.get("selected_supplier"):
            chat_id = ctx.get("chat_id")
            suppliers = list_suppliers(chat_id) if chat_id else []
            if len(suppliers) == 1:
                ctx["selected_supplier"] = suppliers[0]
            else:
                _append_step(
                    run,
                    AgentResult(
                        "system",
                        "blocked",
                        "Pilih vendor: /bayar <nama> — lihat /vendor",
                        {},
                    ),
                )
                run.status = "blocked"
                return run

        ctx["payment_allowed"] = True
        sel = ctx["selected_supplier"]
        ctx["vendor_name"] = sel.get("name")
        ctx["payment_amount"] = int(ctx.get("payment_amount") or sel.get("default_monthly_amount") or 0)

        for agent in [FinanceAgent(), PaymentAgent(), CommunicationAgent(), OperationsAgent()]:
            result = agent.run(ctx)
            _append_step(run, result)
            if result.status in ("blocked", "error"):
                run.status = result.status
                run.context = ctx
                return run
            ctx.update(result.data)

    run.status = "ok"
    run.context = ctx
    return run


def run_vendor_payment_workflow(context: dict[str, Any]) -> WorkflowRun:
    return run_goal_flow(context, UserIntent.VENDOR_PAYMENT)


def run_planning(context: dict[str, Any]) -> WorkflowRun:
    return run_goal_flow(context, UserIntent.PLANNING)
