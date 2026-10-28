import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { NanoRoute, QwenRoute, WanRoute } from "@/lib/studio-admin";
import { validNativeWanId } from "@/lib/studio-system";
import { AdminFeedback, AdminScope, Confirmation } from "./primitives";
import { useSetting } from "./use-setting";

export function ProviderSettings() {
  const [route, setRoute] = useState("wan-standard");
  return <section className="lilac-panel grid gap-3"><h3>Маршруты провайдеров</h3><label>Семейство маршрута<Select value={route} onChange={e => setRoute(e.target.value)}><option value="wan-standard">Wan 3.0 Standard</option><option value="wan-prime">Wan 3.0 Prime</option><option value="qwen-text">Qwen 3.8 · текст</option><option value="qwen-image">Qwen 3.8 · изображение</option><option value="qwen-video">Qwen 3.8 · видео</option><option value="nano">Nano Banana 2.1</option></Select></label>
    <AdminScope key={route}>{route.startsWith("wan-") ? <WanSettings variant={route === "wan-prime" ? "prime" : "standard"} /> : route.startsWith("qwen-") ? <QwenSettings mode={route.slice(5)} /> : <NanoSettings />}</AdminScope>
  </section>;
}
function RouteMeta({ source, actor }: { source: string; actor: number | null }) { return <p>Источник: {source} · Администратор: {actor ?? "не указан"}</p>; }
function WanSettings({ variant }: { variant: "standard" | "prime" }) {
  const setting = useSetting<WanRoute, Pick<WanRoute, "policy" | "neironych_model_id">>(`/admin/provider-routing/wan30/${variant}`, row => ({ policy: row.policy, neironych_model_id: row.neironych_model_id }), row => row.revision);
  const [policy, setPolicy] = useState<WanRoute["policy"]>("kie_only"), [native, setNative] = useState("");
  useEffect(() => { if (setting.data) { setPolicy(setting.data.policy); setNative(setting.data.neironych_model_id); } }, [setting.data]);
  const next = { policy, neironych_model_id: native.trim() }, valid = validNativeWanId(next.neironych_model_id, variant);
  return <div className="grid gap-3"><AdminFeedback busy={setting.busy} error={setting.error} /><Button variant="outline" disabled={setting.busy} onClick={() => void setting.load()}>Обновить настройку</Button>
    {setting.data && <><RouteMeta source={setting.data.source} actor={setting.data.updated_by_admin_tg_id} /><p>Версия: {setting.data.revision} · Ключ Нейроныча: {setting.data.credential_configured === true ? "настроен" : setting.data.credential_configured === false ? "не настроен" : "готовность не сообщена"}</p>
      <label>Политика Wan<Select value={policy} disabled={setting.busy || setting.locked} onChange={e => setPolicy(e.target.value as WanRoute["policy"])}><option value="neironych_kie">Нейроныч → KIE</option><option value="kie_neironych">KIE → Нейроныч</option><option value="neironych_only">Только Нейроныч</option><option value="kie_only">Только KIE</option></Select></label>
      <label>Нативный ID Wan<Input value={native} maxLength={80} disabled={setting.busy || setting.locked} onChange={e => setNative(e.target.value)} /></label><p>ID должен сохранять семейство wan-3 и вариант {variant}. Сервер проверяет каталог Нейроныча при выборе этого провайдера.</p>
      <Button disabled={setting.busy || setting.locked || !valid || !setting.changed(next)} onClick={() => setting.prepare(next)}>Проверить маршрут</Button></>}
    {setting.notice && <p role="status">{setting.notice}</p>}<Confirmation open={Boolean(setting.change)} busy={setting.busy} onCancel={setting.cancel} onConfirm={setting.execute}><p>Wan {variant}: {setting.change?.before.policy} → {setting.change?.next.policy}</p><p>Нативная модель: {setting.change?.before.neironych_model_id} → {setting.change?.next.neironych_model_id}</p><p>Версия {setting.change?.revision}. При конфликте потребуется обновление и новое подтверждение.</p></Confirmation>
  </div>;
}
function QwenSettings({ mode }: { mode: string }) {
  const setting = useSetting<QwenRoute, Pick<QwenRoute, "primary_provider" | "backup_provider">>(`/admin/provider-routing/qwen38/${mode}`, row => ({ primary_provider: row.primary_provider, backup_provider: row.backup_provider }));
  const [primary, setPrimary] = useState<QwenRoute["primary_provider"]>("neironych"), [backup, setBackup] = useState<QwenRoute["backup_provider"]>(null);
  useEffect(() => { if (setting.data) { setPrimary(setting.data.primary_provider); setBackup(setting.data.backup_provider); } }, [setting.data]);
  const next = { primary_provider: primary, backup_provider: backup };
  return <div className="grid gap-3"><AdminFeedback busy={setting.busy} error={setting.error} /><Button variant="outline" disabled={setting.busy} onClick={() => void setting.load()}>Обновить настройку</Button>
    {setting.data && <><RouteMeta source={setting.data.source} actor={setting.data.updated_by_admin_tg_id} /><p>Режим: {setting.data.mode}. Сервер не предоставляет версию; одновременное изменение возможно. Проверяем свежие исходные значения дважды.</p>
      <label>Основной провайдер<Select value={primary} disabled={setting.busy || setting.locked} onChange={e => setPrimary(e.target.value as QwenRoute["primary_provider"])}><option value="neironych">Нейроныч</option><option value="kie">KIE</option></Select></label>
      <label>Резервный провайдер<Select value={backup ?? ""} disabled={setting.busy || setting.locked} onChange={e => setBackup((e.target.value || null) as QwenRoute["backup_provider"])}><option value="">Без резерва</option><option value="neironych">Нейроныч</option><option value="kie">KIE</option></Select></label>
      {primary === backup && <p role="alert">Основной и резервный провайдер должны отличаться.</p>}<Button disabled={setting.busy || setting.locked || primary === backup || !setting.changed(next)} onClick={() => setting.prepare(next)}>Проверить маршрут</Button></>}
    {setting.notice && <p role="status">{setting.notice}</p>}<Confirmation open={Boolean(setting.change)} busy={setting.busy} onCancel={setting.cancel} onConfirm={setting.execute}><p>Qwen · {mode}: основной {setting.change?.before.primary_provider} → {setting.change?.next.primary_provider}; резерв {setting.change?.before.backup_provider ?? "нет"} → {setting.change?.next.backup_provider ?? "нет"}.</p></Confirmation>
  </div>;
}
function NanoSettings() {
  const setting = useSetting<NanoRoute, Pick<NanoRoute, "primary_provider">>("/admin/provider-routing/nano-banana-2.1", row => ({ primary_provider: row.primary_provider }));
  const [primary, setPrimary] = useState<NanoRoute["primary_provider"]>("neironych");
  useEffect(() => { if (setting.data) setPrimary(setting.data.primary_provider); }, [setting.data]);
  const next = { primary_provider: primary };
  return <div className="grid gap-3"><AdminFeedback busy={setting.busy} error={setting.error} /><Button variant="outline" disabled={setting.busy} onClick={() => void setting.load()}>Обновить настройку</Button>
    {setting.data && <><RouteMeta source={setting.data.source} actor={setting.data.updated_by_admin_tg_id} /><p>{setting.data.model_key}. Сервер не предоставляет версию; одновременное изменение возможно.</p><label>Основной провайдер<Select value={primary} disabled={setting.busy || setting.locked} onChange={e => setPrimary(e.target.value as NanoRoute["primary_provider"])}><option value="neironych">Нейроныч</option><option value="nexus">Nexus</option></Select></label><Button disabled={setting.busy || setting.locked || !setting.changed(next)} onClick={() => setting.prepare(next)}>Проверить маршрут</Button></>}
    {setting.notice && <p role="status">{setting.notice}</p>}<Confirmation open={Boolean(setting.change)} busy={setting.busy} onCancel={setting.cancel} onConfirm={setting.execute}><p>Nano Banana 2.1: {setting.change?.before.primary_provider} → {setting.change?.next.primary_provider}</p></Confirmation>
  </div>;
}
