import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { AdminFeedback, Confirmation } from "./primitives";
import { useSetting } from "./use-setting";

type Audience = "admin" | "public" | "disabled";
export function ContentSettings() {
  return <section className="grid gap-3"><KlingAccess /><FeedIdentity /></section>;
}
function KlingAccess() {
  const setting = useSetting<{ audience: Audience }, { audience: Audience }>("/admin/kling4/access", row => ({ audience: row.audience }));
  const [audience, setAudience] = useState<Audience>("admin");
  useEffect(() => { if (setting.data) setAudience(setting.data.audience); }, [setting.data]);
  const next = { audience };
  return <article className="lilac-panel grid gap-3"><h3>Доступ к Kling 4</h3><p>Эта настройка управляет моделью Kling 4 во всех применимых каналах. Новый интерфейс Studio по-прежнему доступен только администраторам. Сервер не предоставляет версию; одновременное изменение возможно.</p><AdminFeedback busy={setting.busy} error={setting.error} /><Button variant="outline" disabled={setting.busy} onClick={() => void setting.load()}>Обновить доступ</Button>
    {setting.data && <><label>Аудитория Kling 4<Select value={audience} disabled={setting.busy || setting.locked} onChange={e => setAudience(e.target.value as Audience)}><option value="admin">Только администраторы</option><option value="public">Все пользователи</option><option value="disabled">Отключено</option></Select></label><Button disabled={setting.busy || setting.locked || !setting.changed(next)} onClick={() => setting.prepare(next)}>Проверить доступ</Button></>}
    {setting.notice && <p role="status">{setting.notice}</p>}<Confirmation open={Boolean(setting.change)} busy={setting.busy} onCancel={setting.cancel} onConfirm={setting.execute}><p>Kling 4: {setting.change?.before.audience} → {setting.change?.next.audience}.</p>{setting.change?.next.audience === "public" && <p>Вы открываете Kling 4 всем пользователям. Они смогут запускать доступные генерации этой модели. Подтвердите публичное открытие.</p>}</Confirmation>
  </article>;
}
function FeedIdentity() {
  const setting = useSetting<{ instruction: string }, { instruction: string }>("/admin/feed-recipe-identity", row => ({ instruction: row.instruction }));
  const [instruction, setInstruction] = useState("");
  useEffect(() => { if (setting.data) setInstruction(setting.data.instruction); }, [setting.data]);
  const next = { instruction: instruction.trim() }, length = Array.from(next.instruction).length, valid = length >= 100 && length <= 3000;
  return <article className="lilac-panel grid gap-3"><h3>Идентичность рецептов ленты</h3><p>Административная политика обработки рецептов. Инструкция хранится только на сервере и в памяти открытой формы. Сервер не предоставляет версию; одновременное изменение возможно.</p><AdminFeedback busy={setting.busy} error={setting.error} /><Button variant="outline" disabled={setting.busy} onClick={() => void setting.load()}>Обновить инструкцию</Button>
    {setting.data && <><label>Инструкция идентичности<textarea className="min-h-44 w-full rounded-xl border p-3" maxLength={6000} disabled={setting.busy || setting.locked} value={instruction} onChange={e => setInstruction(e.target.value)} /></label><p>{length} / 3000 символов. Минимум 100 после удаления пробелов по краям.</p><Button disabled={setting.busy || setting.locked || !valid || !setting.changed(next)} onClick={() => setting.prepare(next)}>Проверить инструкцию</Button></>}
    {setting.notice && <p role="status">{setting.notice}</p>}<Confirmation open={Boolean(setting.change)} busy={setting.busy} onCancel={setting.cancel} onConfirm={setting.execute}><p>Заменить административную инструкцию идентичности?</p><p className="whitespace-pre-wrap break-words">{setting.change?.next.instruction}</p></Confirmation>
  </article>;
}
