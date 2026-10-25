import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { MiniAppApi } from "@/lib/api";
import { AdminScope, useAdminSession } from "./primitives";
import { ProviderSettings } from "./provider-settings";
import { RecoverySettings } from "./recovery-settings";
import { SupplierReviews } from "./supplier-reviews";
import { TributeProducts } from "./tribute-products";
import { ContentSettings } from "./content-settings";

export function LilacAdminSystemPanel({ api: _api, ownerId }: { api: MiniAppApi; ownerId: number }) {
  const session = useAdminSession(), [tab, setTab] = useState("");
  if (session.ownerId !== ownerId || !session.active()) return null;
  const sections = [["providers", "Маршруты провайдеров"], ["recovery", "Автовозврат изображений"], ["suppliers", "Сверка поставщиков"], ["tribute", "Каталог Tribute"], ["content", "Контент и доступ"]];
  return <section className="grid min-w-0 gap-3"><h2>Настройки системы</h2><p>Выберите раздел. Каждое изменение проверяется по текущим данным и требует отдельного подтверждения.</p>
    <nav className="flex flex-wrap gap-2" aria-label="Разделы настроек системы">{sections.map(([key, label]) => <Button className="h-auto whitespace-normal" key={key} variant={tab === key ? "default" : "outline"} aria-pressed={tab === key} onClick={() => setTab(key)}>{label}</Button>)}</nav>
    <AdminScope key={tab}>{tab === "providers" && <ProviderSettings />}{tab === "recovery" && <RecoverySettings />}{tab === "suppliers" && <SupplierReviews />}{tab === "tribute" && <TributeProducts />}{tab === "content" && <ContentSettings />}</AdminScope>
  </section>;
}
