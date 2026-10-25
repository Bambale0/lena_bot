import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatCredits } from "@/lib/utils";
import type { LedgerRow } from "@/lib/studio-admin";
import { AdminFeedback, useAdminMutation, useAdminSession } from "./primitives";

export function AdminLedger() {
  const session = useAdminSession(), load = useAdminMutation();
  const [userId, setUserId] = useState(""), [rows, setRows] = useState<LedgerRow[] | null>(null);
  const valid = !userId || /^[1-9]\d*$/.test(userId) && Number.isSafeInteger(Number(userId));
  return <section className="lilac-panel grid gap-3"><h2>Журнал баланса</h2><p>Последние 50 записей. Пустой ID показывает общий журнал. Это ограниченная выборка, а не полная история.</p>
    <form className="grid gap-2" onSubmit={e => { e.preventDefault(); if (valid) void load.run(async () => { setRows(null); const result = await session.requestWeb<{ items: LedgerRow[] }>(`/admin/ledger?${userId ? `user_id=${userId}&` : ""}limit=50`); setRows(result.items); }); }}><label>ID аккаунта для журнала<Input inputMode="numeric" value={userId} onChange={e => setUserId(e.target.value)} /></label><Button type="submit" disabled={!valid || load.busy}>Загрузить журнал</Button></form>
    <AdminFeedback busy={load.busy} error={load.error} />
    {rows?.map(row => <article className="lilac-panel break-words" key={row.id}><strong>#{row.id} · Аккаунт #{row.user_id} · {row.delta > 0 ? "+" : ""}{formatCredits(row.delta)} кр.</strong><p>Баланс после: {formatCredits(row.balance_after)} кр.</p><p>{row.entry_type} · {row.source_type || "—"} / {row.source_id || "—"}</p><p>{row.note || "Без комментария"}</p><small>{row.created_at}</small></article>)}
    {rows?.length === 0 && <p>Записей нет.</p>}
  </section>;
}
