import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import type { MiniAppApi } from "@/lib/api";
import { AdminOperations } from "./operations";
import { AdminPricing } from "./pricing";
import { AdminLedger } from "./ledger";
import { AdminPublishedPrompts } from "./published-prompts";
import { AdminScope, useAdminSession } from "./primitives";
import "./admin.css";

/** Must be under AdminBoundary with the same actor. systemPanel shares its request safeguards. */
export function LilacAdminWorkspace({ api: _api, ownerId, systemPanel }: { api: MiniAppApi; ownerId: number; systemPanel?: ReactNode }) {
  const session = useAdminSession();
  const [tab, setTab] = useState("");
  if (session.ownerId !== ownerId || !session.active()) return null;
  const sections = [["queue", "Очередь генераций"], ["pricing", "Цены и пакеты"], ["ledger", "Журнал баланса"], ["prompts", "Опубликованные промпты"], ...(systemPanel ? [["system", "Настройки системы"]] : [])];
  return <section className="lilac-admin-workspace grid gap-3"><h2>Операционные инструменты</h2><nav aria-label="Административные инструменты" className="flex flex-wrap gap-2">{sections.map(([key, label]) => <Button key={key} variant={tab === key ? "default" : "outline"} aria-pressed={tab === key} onClick={() => setTab(key)}>{label}</Button>)}</nav>
    <AdminScope key={tab}>{tab === "queue" && <AdminOperations />}{tab === "pricing" && <AdminPricing />}{tab === "ledger" && <AdminLedger />}{tab === "prompts" && <AdminPublishedPrompts />}{tab === "system" && systemPanel}</AdminScope>
  </section>;
}
