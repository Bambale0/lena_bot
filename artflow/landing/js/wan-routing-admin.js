"use strict";
(() => {
  const form = document.getElementById("wan-routing");
  const status = document.getElementById("wan-status");
  const field = name => form.elements.namedItem(name);
  let revision = null;
  let busy = false;
  const show = text => { status.textContent = text; };
  function lock(value) {
    busy = value;
    form.querySelectorAll("input,select,button").forEach(element => { element.disabled = value; });
  }
  async function request(method, body) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    const headers = {"Content-Type": "application/json"};
    const initData = window.Telegram?.WebApp?.initData;
    if (initData) headers["X-Telegram-Init-Data"] = initData;
    try {
      const response = await fetch("/api/web/admin/provider-routing/wan30/" + field("variant").value, {
        method, body: body ? JSON.stringify(body) : undefined,
        headers, credentials: "same-origin", signal: controller.signal,
      });
      const payload = await response.json();
      if (!response.ok || payload.ok === false) {
        if (response.status === 401) throw Error("Войдите в кабинет или откройте страницу из бота.");
        if (response.status === 403) throw Error("Нужны права администратора.");
        throw Error(typeof payload.error === "string" ? payload.error : "Не удалось сохранить настройки.");
      }
      return payload.data;
    } finally { clearTimeout(timer); }
  }
  async function load() {
    revision = null;
    const row = await request("GET");
    field("policy").value = row.policy;
    field("neironych_model_id").value = row.neironych_model_id;
    revision = row.revision;
    form.hidden = false;
    show(`Версия ${row.revision}. ${row.credential_configured ? "Ключ Нейроныча настроен." : "Ключ Нейроныча не настроен: используется KIE, если резерв разрешён."}`);
  }
  async function reload() {
    if (busy) return;
    lock(true);
    try { await load(); } catch (error) { show(error.message); } finally { lock(false); }
  }
  field("variant").addEventListener("change", reload);
  document.getElementById("wan-reload").addEventListener("click", reload);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (busy || revision === null || !form.reportValidity()) return;
    const body = {policy: field("policy").value, neironych_model_id: field("neironych_model_id").value.trim(), expected_revision: revision};
    lock(true);
    try {
      await request("PUT", body);
      await load();
      show("Сохранено в БД и журнале. Новые задачи используют этот маршрут без деплоя.");
    } catch (error) {
      revision = null;
      show(error.name === "AbortError" || error instanceof TypeError
        ? "Ответ не получен. Изменение могло сохраниться. Нажмите «Обновить» перед повтором."
        : error.message + " Нажмите «Обновить» перед повтором.");
    } finally { lock(false); }
  });
  window.Telegram?.WebApp?.ready?.();
  reload();
})();
