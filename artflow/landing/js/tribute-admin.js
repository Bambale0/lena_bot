"use strict";
const form = document.getElementById("catalog-form");
const picker = document.getElementById("catalog-select");
const notice = document.getElementById("catalog-status");
const field = name => form.elements.namedItem(name);
let products = [];
let saving = false;
function show(text) { notice.textContent = text; }
async function catalogRequest(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  const headers = {"Content-Type": "application/json"};
  const telegramData = window.Telegram?.WebApp?.initData;
  if (telegramData) headers["X-Telegram-Init-Data"] = telegramData;
  try {
    const response = await fetch("/api/web/admin/payments/tribute-products" + path,
      {...options, headers, credentials: "same-origin", signal: controller.signal});
    const body = await response.json();
    if (!response.ok || body.ok === false) {
      if (response.status === 401) throw Error("Войдите в кабинет или откройте страницу из Telegram-бота.");
      if (response.status === 403) throw Error("Нужны права администратора.");
      if (response.status === 409) throw Error("Обновите каталог: версия изменилась или требуется новый product ID.");
      throw Error(typeof body.error === "string" ? body.error : "Проверка не пройдена.");
    }
    return body.data;
  } finally { clearTimeout(timer); }
}
function populate() {
  const row = products.find(item => String(item.product_id) === picker.value);
  for (const name of ["product_id", "plan_key", "payment_url", "amount_minor"]) field(name).value = row?.[name] || "";
  field("enabled").checked = row ? row.enabled : true;
  field("expected_revision").value = row?.revision || 0;
  field("product_id").readOnly = Boolean(row);
  show(row ? `Версия ${row.revision}. Условия: ${row.credits} кредитов, ${row.amount_rub} ₽.` : "Новый продукт. Используйте ключ пакета из прайс-листа.");
}
async function load(selected = "") {
  const response = await catalogRequest("");
  products = Array.isArray(response?.items) ? response.items : [];
  picker.replaceChildren(new Option("Новый продукт", ""));
  for (const row of products) picker.add(new Option(`${row.plan_key} · ${row.product_id} · ${row.enabled ? "активен" : "архив"}`, String(row.product_id)));
  picker.value = products.some(row => String(row.product_id) === selected) ? selected : "";
  form.hidden = false;
  populate();
}
function lock(value) {
  saving = value;
  form.querySelectorAll("button").forEach(button => { button.disabled = value; });
}
picker.addEventListener("change", populate);
document.getElementById("catalog-reload").addEventListener("click", async () => {
  if (saving) return;
  lock(true);
  try { await load(picker.value); } catch (error) { show(error.message); } finally { lock(false); }
});
form.addEventListener("submit", async event => {
  event.preventDefault();
  if (saving || !form.reportValidity()) return;
  const productId = Number(field("product_id").value);
  const amount = Number(field("amount_minor").value);
  if (!Number.isSafeInteger(productId) || productId < 1 || !Number.isSafeInteger(amount) || amount < 1) {
    show("ID и цена должны быть положительными целыми числами."); return;
  }
  const body = {plan_key: field("plan_key").value.trim(), payment_url: field("payment_url").value.trim(),
    currency: "usd", amount_minor: amount, enabled: field("enabled").checked,
    expected_revision: Number(field("expected_revision").value)};
  lock(true);
  try {
    await catalogRequest("/" + productId, {method: "PUT", body: JSON.stringify(body)});
    await load(String(productId));
    show("Сохранено в каталоге и журнале. Новые экраны оплаты используют эту версию без деплоя.");
  } catch (error) {
    show(error.name === "AbortError" || error instanceof TypeError
      ? "Ответ не получен. Сохранение могло завершиться: обновите каталог перед повтором."
      : error.message);
  } finally { lock(false); }
});
window.Telegram?.WebApp?.ready?.();
load().catch(error => show(error.message));
