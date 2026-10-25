import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { RecoveryPolicy } from "@/lib/studio-admin";
import { humanDeadline, recoverySeconds } from "@/lib/studio-system";
import { AdminFeedback, AdminScope, Confirmation } from "./primitives";
import { useSetting } from "./use-setting";

export function RecoverySettings() {
  const [provider, setProvider] = useState("neironych");
  return <section className="lilac-panel grid gap-3"><h3>Автовозврат изображений</h3><label>Провайдер автовозврата<Select value={provider} onChange={e => setProvider(e.target.value)}><option value="neironych">Нейроныч</option><option value="nexus">Nexus</option></Select></label><AdminScope key={provider}><RecoveryForm provider={provider} /></AdminScope></section>;
}
function RecoveryForm({ provider }: { provider: string }) {
  const setting = useSetting<RecoveryPolicy, Pick<RecoveryPolicy, "auto_refund_seconds">>(`/admin/image-recovery/${provider}`, row => ({ auto_refund_seconds: row.auto_refund_seconds }));
  const [seconds, setSeconds] = useState("");
  useEffect(() => { if (setting.data) setSeconds(String(setting.data.auto_refund_seconds)); }, [setting.data]);
  const parsed = recoverySeconds(seconds), next = { auto_refund_seconds: parsed ?? 0 };
  return <div className="grid gap-3"><AdminFeedback busy={setting.busy} error={setting.error} /><Button variant="outline" disabled={setting.busy} onClick={() => void setting.load()}>Обновить настройку</Button>
    {setting.data && <><p>Источник: {setting.data.source} · Текущий срок: {humanDeadline(setting.data.auto_refund_seconds)}. Сервер не предоставляет версию; одновременное изменение возможно.</p><label>Срок автовозврата, секунды<Input type="number" min={600} max={86400} step={1} value={seconds} disabled={setting.busy || setting.locked} onChange={e => setSeconds(e.target.value)} /></label><p>{parsed ? humanDeadline(parsed) : "Введите целое число от 600 до 86400 секунд."} Автовозврат не означает отмену задачи у поставщика.</p><Button disabled={setting.busy || setting.locked || parsed === null || !setting.changed(next)} onClick={() => setting.prepare(next)}>Проверить срок</Button></>}
    {setting.notice && <p role="status">{setting.notice}</p>}<Confirmation open={Boolean(setting.change)} busy={setting.busy} onCancel={setting.cancel} onConfirm={setting.execute}><p>{provider}: {setting.change?.before.auto_refund_seconds} → {setting.change?.next.auto_refund_seconds} секунд.</p></Confirmation>
  </div>;
}
