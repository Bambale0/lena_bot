import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import type { MiniAppApi } from "@/lib/api";
import { safeExternalUrl } from "@/lib/utils";

export interface ImageSeries {
  id: number; model: string; mode: string; aspect_ratio?: string; quality: string; count: number;
  base_prompt?: string; last_prompt?: string; prompt_hidden?: boolean; prompt_actions_allowed?: boolean;
  prompt_unavailable_reason?: string; reference_url?: string; reference_urls?: string[]; last_result_url?: string;
}

export function LilacImageSeries({ api, onContinue }: { api: MiniAppApi; onContinue: (series: ImageSeries) => void }) {
  const [series, setSeries] = useState<ImageSeries | null>(null), [error, setError] = useState(""), [busy, setBusy] = useState(false), [confirm, setConfirm] = useState(false);
  useEffect(() => { const controller = new AbortController();
    api.requestWeb<ImageSeries | null>("/image-sessions/active", {}, controller.signal).then(row => { if (!controller.signal.aborted) setSeries(row); }).catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Не удалось загрузить серию"); });
    return () => controller.abort();
  }, [api]);
  const archive = async () => {
    if (!series || busy) return; setBusy(true); setError("");
    try { await api.requestWeb(`/image-sessions/${series.id}/archive`, { method: "POST", body: "{}" }); setSeries(null); }
    catch (e) { setError(e instanceof Error ? e.message : "Не удалось завершить серию"); } finally { setBusy(false); }
  };
  return <section className="lilac-image-series">{error && <p role="alert">{error}</p>}{series && <><h2>Последняя серия фото</h2><div className="lilac-row">{safeExternalUrl(series.last_result_url) && <img width="64" height="64" src={safeExternalUrl(series.last_result_url)} alt="Последний результат серии" />}<p>{series.model}</p></div><p className="lilac-note">Серия сохраняет исходные фото и параметры. Это не монтажный проект.</p>{series.prompt_hidden && <p role="status">{series.prompt_unavailable_reason || "Текст автора скрыт. Введите собственное описание."}</p>}<div className="flex flex-wrap gap-2"><Button onClick={() => setConfirm(true)}>Продолжить серию</Button><Button variant="outline" disabled={busy} onClick={() => void archive()}>Завершить серию</Button></div></>}
    <Sheet open={confirm && Boolean(series)} title="Восстановить серию?" onOpenChange={setConfirm} footer={<Button onClick={() => { if (series) onContinue(series); setConfirm(false); }}>Заменить черновик фото</Button>}><p>Фото и параметры серии заменят текущий черновик фото. Скрытый текст автора не восстанавливается. Перед новым запуском проверьте описание и стоимость.</p></Sheet>
  </section>;
}
