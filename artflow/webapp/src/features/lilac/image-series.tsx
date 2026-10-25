import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import type { MiniAppApi } from "@/lib/api";
import type { ModelInfo } from "@/lib/types";
import { safeExternalUrl } from "@/lib/utils";
import { LilacCreateImageSeries } from "./create-image-series";
import { useConsumerWrite } from "./use-consumer-write";

export interface ImageSeries {
  id: number; model: string; mode: string; aspect_ratio?: string; quality: string; count: number;
  base_prompt?: string; last_prompt?: string; prompt_hidden?: boolean; prompt_actions_allowed?: boolean;
  prompt_unavailable_reason?: string; reference_url?: string; reference_urls?: string[]; last_result_url?: string;
}

export function LilacImageSeries({ api, onContinue, models = [] }: { api: MiniAppApi; onContinue: (series: ImageSeries) => void; models?: ModelInfo[] }) {
  const [series, setSeries] = useState<ImageSeries | null>(null), [error, setError] = useState(""), [loading, setLoading] = useState(true), [confirm, setConfirm] = useState(false), [creating, setCreating] = useState(false), [archiveConfirm, setArchiveConfirm] = useState(false), [success, setSuccess] = useState(false);
  const write = useConsumerWrite();
  useEffect(() => { const controller = new AbortController();
    const deadline = window.setTimeout(() => { controller.abort(); setLoading(false); setError("Не удалось дождаться активной серии. Обновите страницу."); }, 20_000);
    api.requestWeb<ImageSeries | null>("/image-sessions/active", {}, controller.signal).then(row => { if (!controller.signal.aborted) setSeries(row?.id ? row : null); }).catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Не удалось загрузить серию"); }).finally(() => { window.clearTimeout(deadline); if (!controller.signal.aborted) setLoading(false); });
    return () => { window.clearTimeout(deadline); controller.abort(); };
  }, [api]);
  const archive = async () => {
    if (!series) return;
    await write.run(signal => api.requestWeb(`/image-sessions/${series.id}/archive`, { method: "POST", body: "{}" }, signal), () => { setSeries(null); setArchiveConfirm(false); });
  };
  return <section className="lilac-image-series">{error && <p role="alert">{error}</p>}{write.error && !archiveConfirm && <p role="alert">{write.error}</p>}{loading && <p role="status">Загружаем серию…</p>}{success && <p role="status">Серия создана</p>}<Button variant="outline" disabled={loading || write.busy || write.unauthorized} onClick={() => { setSuccess(false); setCreating(true); }}>Создать серию фото</Button>{!series && !loading && !error && <p className="lilac-note">Сохраните исходники и параметры серии без запуска генерации.</p>}{series && <><h2>Последняя серия фото</h2><div className="lilac-row">{safeExternalUrl(series.last_result_url) && <img width="64" height="64" src={safeExternalUrl(series.last_result_url)} alt="Последний результат серии" />}<p>{models.find(model => model.key === series.model)?.display_name || series.model}</p></div><p className="lilac-note">Серия сохраняет исходные фото и параметры. Это не монтажный проект.</p>{series.prompt_hidden && <p role="status">{series.prompt_unavailable_reason || "Текст автора скрыт. Введите собственное описание."}</p>}<div className="flex flex-wrap gap-2"><Button onClick={() => setConfirm(true)}>Продолжить серию</Button><Button variant="outline" disabled={write.busy || write.unauthorized} onClick={() => setArchiveConfirm(true)}>Завершить серию</Button></div></>}
    <Sheet open={confirm && Boolean(series)} title="Восстановить серию?" onOpenChange={setConfirm} footer={<Button onClick={() => { if (series) onContinue(series); setConfirm(false); }}>Заменить черновик фото</Button>}><p>Фото и параметры серии заменят текущий черновик фото. Скрытый текст автора не восстанавливается. Перед новым запуском проверьте описание и стоимость.</p></Sheet>
    <Sheet open={archiveConfirm} title="Завершить серию?" onOpenChange={setArchiveConfirm} footer={<Button disabled={write.busy || write.unauthorized} onClick={() => void archive()}>Подтвердить завершение серии</Button>}><p>Активная серия будет завершена. Её работы останутся в проектах.</p>{write.error && <p role="alert">{write.error}</p>}</Sheet>
    {creating && <LilacCreateImageSeries api={api} models={models} onClose={() => setCreating(false)} onCreated={row => { setSeries(row); setCreating(false); setSuccess(true); setError(""); }} />}
  </section>;
}
