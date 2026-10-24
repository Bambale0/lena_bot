import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ApiError, type MiniAppApi } from "@/lib/api";
import { safeExternalUrl } from "@/lib/utils";

interface Profile { id: number; full_name?: string; username?: string; email?: string; phone?: string; photo_url?: string; language?: string; has_password?: boolean; }
const message = (error: unknown) => error instanceof Error ? error.message : "Не удалось сохранить. Повторите попытку.";

export function LilacAccountEditor({ api, ownerId, onSaved }: { api: MiniAppApi; ownerId: number; onSaved: () => void }) {
  const [profile, setProfile] = useState<Profile | null>(null), [loading, setLoading] = useState(true), [loadError, setLoadError] = useState("");
  const [form, setForm] = useState({ full_name: "", username: "", email: "", phone: "", photo_url: "", language: "ru" });
  const [busy, setBusy] = useState(false), [profileError, setProfileError] = useState(""), [profileStatus, setProfileStatus] = useState("");
  const [currentPassword, setCurrentPassword] = useState(""), [newPassword, setNewPassword] = useState(""), [confirmation, setConfirmation] = useState("");
  const [passwordError, setPasswordError] = useState(""), [passwordStatus, setPasswordStatus] = useState("");
  const mutation = useRef(false), lifetime = useRef(new AbortController());
  const load = async (signal: AbortSignal) => {
    setLoading(true); setLoadError("");
    try { const row = await api.requestWeb<Profile>("/me", { cache: "no-store" }, signal);
      if (row.id !== ownerId) throw new Error("Аккаунт изменился. Откройте профиль заново.");
      if (!signal.aborted) { setProfile(row); setForm({ full_name: row.full_name || "", username: row.username || "", email: row.email || "", phone: row.phone || "", photo_url: row.photo_url || "", language: row.language === "en" ? "en" : "ru" }); }
    } catch (e) { if (!signal.aborted) setLoadError(message(e)); } finally { if (!signal.aborted) setLoading(false); }
  };
  useEffect(() => { const controller = new AbortController(); lifetime.current = controller; void load(controller.signal); return () => controller.abort(); }, [api, ownerId]);
  const saveProfile = async () => {
    if (!profile || mutation.current) return; mutation.current = true; setBusy(true); setProfileError(""); setProfileStatus("");
    const signal = lifetime.current.signal;
    try { const row = await api.requestWeb<Profile>("/me/profile", { method: "PUT", body: JSON.stringify(form) }, signal);
      if (row.id !== ownerId) throw new Error("Аккаунт изменился. Обновите приложение.");
      if (!signal.aborted) { setProfile(row); setProfileStatus("Профиль сохранён"); onSaved(); }
    } catch (e) { if (!signal.aborted) setProfileError(message(e)); } finally { mutation.current = false; if (!signal.aborted) setBusy(false); }
  };
  const uploadPhoto = async (file: File) => {
    if (mutation.current) return;
    if (!file.type.startsWith("image/")) { setProfileError("Выберите изображение для аватара."); return; }
    mutation.current = true; setBusy(true); setProfileError(""); setProfileStatus("");
    const signal = lifetime.current.signal;
    try { const upload = await api.uploadMedia(file, signal); const url = safeExternalUrl(upload.url);
      if (!url || upload.kind && upload.kind !== "image") throw new Error("Сервер не подтвердил загрузку изображения.");
      if (!signal.aborted) { setForm(current => ({ ...current, photo_url: url })); setProfileStatus("Фото загружено. Сохраните профиль, чтобы применить его."); }
    } catch (e) { if (!signal.aborted) setProfileError(message(e)); } finally { mutation.current = false; if (!signal.aborted) setBusy(false); }
  };
  const validPassword = newPassword.length >= 8 && newPassword.length <= 128 && newPassword === confirmation && (!profile?.has_password || Boolean(currentPassword));
  const savePassword = async () => {
    if (!profile || mutation.current || !validPassword) return; mutation.current = true; setBusy(true); setPasswordError(""); setPasswordStatus("");
    const signal = lifetime.current.signal;
    try { const row = await api.requestWeb<Profile>("/me/password", { method: "PUT", body: JSON.stringify({ current_password: currentPassword || undefined, new_password: newPassword }) }, signal);
      if (row.id !== ownerId) throw new Error("Аккаунт изменился. Обновите приложение.");
      if (!signal.aborted) { setProfile(row); setCurrentPassword(""); setNewPassword(""); setConfirmation(""); setPasswordStatus("Пароль сохранён"); }
    } catch (e) { if (!signal.aborted) setPasswordError(e instanceof ApiError ? e.message : "Ответ не получен. Пароль мог измениться — проверьте вход на сайте перед повтором."); }
    finally { mutation.current = false; if (!signal.aborted) setBusy(false); }
  };
  const field = (key: keyof typeof form, value: string) => { setForm(current => ({ ...current, [key]: value })); setProfileStatus(""); };
  return <div className="lilac-page"><header className="lilac-title"><p>Ваш аккаунт</p><h1>Редактировать профиль</h1><span>Данные профиля и вход на сайт. Telegram-подключение сохраняется.</span></header>
    {loading ? <p role="status">Загружаем профиль…</p> : loadError ? <div role="alert"><p>{loadError}</p><Button onClick={() => void load(lifetime.current.signal)}>Повторить</Button></div> : profile && <>
      <form className="lilac-panel" aria-label="Данные профиля" onSubmit={event => { event.preventDefault(); void saveProfile(); }}>
        <h2>Данные профиля</h2><div className="lilac-avatar-edit">{safeExternalUrl(form.photo_url) && <img src={safeExternalUrl(form.photo_url)} alt="Фото профиля" />}<label>Новое фото<input aria-label="Новое фото профиля" type="file" accept="image/*" disabled={busy} onChange={event => { const file = event.target.files?.[0]; if (file) void uploadPhoto(file); event.target.value = ""; }} /></label>{form.photo_url && <Button type="button" variant="outline" disabled={busy} onClick={() => field("photo_url", "")}>Убрать фото профиля</Button>}</div>
        <label>Имя в профиле<Input value={form.full_name} maxLength={256} autoComplete="name" disabled={busy} onChange={e => field("full_name", e.target.value)} /></label>
        <label>Username<Input value={form.username} maxLength={64} autoComplete="username" disabled={busy} onChange={e => field("username", e.target.value)} /></label>
        <label>Email<Input type="email" value={form.email} maxLength={256} autoComplete="email" disabled={busy} onChange={e => field("email", e.target.value)} /></label>
        <label>Телефон<Input type="tel" value={form.phone} maxLength={32} autoComplete="tel" placeholder="В международном формате" disabled={busy} onChange={e => field("phone", e.target.value)} /></label>
        <label>Язык сообщений<Select value={form.language} disabled={busy} onChange={e => field("language", e.target.value)}><option value="ru">Русский</option><option value="en">English</option></Select></label>
        {profileError && <p role="alert">{profileError}</p>}{profileStatus && <p role="status">{profileStatus}</p>}
        <Button type="submit" disabled={busy}>{busy ? "Сохраняем…" : "Сохранить профиль"}</Button>
      </form>
      <form className="lilac-panel" aria-label="Пароль для сайта" onSubmit={event => { event.preventDefault(); void savePassword(); }}>
        <h2>{profile.has_password ? "Сменить пароль для сайта" : "Установить пароль для сайта"}</h2><p>Пароль не нужен для входа через Telegram. Для сайта используйте email, телефон или username, указанные в профиле.</p>
        {profile.has_password && <label>Текущий пароль<Input type="password" value={currentPassword} maxLength={128} autoComplete="current-password" disabled={busy} required onChange={e => setCurrentPassword(e.target.value)} /></label>}
        <label>Новый пароль<Input type="password" value={newPassword} minLength={8} maxLength={128} autoComplete="new-password" disabled={busy} required onChange={e => setNewPassword(e.target.value)} /></label>
        <label>Повторите новый пароль<Input type="password" value={confirmation} minLength={8} maxLength={128} autoComplete="new-password" disabled={busy} required onChange={e => setConfirmation(e.target.value)} /></label>
        {confirmation && confirmation !== newPassword && <p role="status">Пароли должны совпадать.</p>}<p className="lilac-note">От 8 до 128 символов. Пароль не сохраняется в браузерном хранилище приложения.</p>
        {passwordError && <p role="alert">{passwordError}</p>}{passwordStatus && <p role="status">{passwordStatus}</p>}
        <Button type="submit" disabled={busy || !validPassword}>Сохранить пароль</Button>
      </form>
    </>}
  </div>;
}
