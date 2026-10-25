import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { AdminPrompt } from "@/lib/studio-admin";
import { AdminFeedback, Confirmation, useAdminMutation, useAdminSession } from "./primitives";

export function AdminPublishedPrompts() {
  const session = useAdminSession(), mutation = useAdminMutation();
  const [id, setId] = useState(""), [catalog, setCatalog] = useState<AdminPrompt[] | null>(null), [selected, setSelected] = useState<AdminPrompt | null>(null), [confirm, setConfirm] = useState(false);
  const [notice, setNotice] = useState("");
  const inspect = (target: number) => void mutation.run(async () => { setSelected(null); setNotice(""); setSelected(await session.requestWeb<AdminPrompt>(`/prompts/${target}`)); });
  const execute = () => void mutation.run(async () => {
    if (!selected || !confirm) return;
    try {
      const fresh = await session.requestWeb<AdminPrompt>(`/prompts/${selected.id}`);
      if (fresh.id !== selected.id || fresh.title !== selected.title || fresh.prompt_text !== selected.prompt_text || fresh.status !== selected.status || fresh.status !== "approved") throw new Error("Промпт изменился. Откройте его заново.");
      const response = await session.requestWeb<AdminPrompt>(`/admin/prompts/${selected.id}/deactivate`, { method: "POST", body: "{}" });
      if (response.id !== selected.id || response.status !== "deactivated") throw new Error("Снятие с публикации не подтверждено. Проверьте промпт заново.");
      setSelected(response); setNotice("Промпт снят с публикации.");
    } finally { if (session.active()) setConfirm(false); }
  });
  return <section className="lilac-panel grid gap-3"><h2>Опубликованные промпты</h2><p>Откройте точный ID или выберите из первых 40 работ публичного каталога.</p>
    <form className="grid gap-2" onSubmit={e => { e.preventDefault(); if (/^[1-9]\d*$/.test(id) && Number.isSafeInteger(Number(id))) inspect(Number(id)); }}><label>ID промпта<Input inputMode="numeric" value={id} onChange={e => setId(e.target.value)} /></label><Button type="submit" disabled={mutation.busy || !/^[1-9]\d*$/.test(id) || !Number.isSafeInteger(Number(id))}>Открыть промпт</Button></form>
    <Button variant="outline" disabled={mutation.busy} onClick={() => void mutation.run(async () => { const rows = await session.requestWeb<{ items: AdminPrompt[] }>("/prompts?source=catalog&page=1&limit=40"); setCatalog(rows.items); })}>Загрузить публичный каталог</Button>
    <AdminFeedback busy={mutation.busy} error={mutation.error} />{notice && <p role="status">{notice}</p>}
    {catalog?.map(row => <Button key={row.id} variant="outline" className="h-auto min-h-11 whitespace-normal" disabled={mutation.busy} onClick={() => inspect(row.id)}>#{row.id} · {row.title}</Button>)}{catalog?.length === 0 && <p>Каталог пуст.</p>}
    {selected && <article className="lilac-panel break-words"><h3>{selected.title}</h3><p>ID {selected.id} · {selected.model} · {selected.status}</p><p>{selected.description}</p><p>{selected.prompt_text}</p><Button disabled={mutation.busy || selected.status !== "approved"} onClick={() => setConfirm(true)}>Снять с публикации</Button></article>}
    <Confirmation open={confirm} busy={mutation.busy} onCancel={() => setConfirm(false)} onConfirm={execute}><p>Снять с публикации промпт #{selected?.id} «{selected?.title}»? Он перестанет быть доступен в общем каталоге.</p></Confirmation>
  </section>;
}
