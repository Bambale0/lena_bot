import React, { useEffect, useState } from "react";
import Icon from "./icons.jsx";
import {
  api,
  formatCredits,
  openExternal,
  useResource,
} from "./api.js";
import { Loading } from "./components.jsx";

export default function TopupModal({ user, onClose, onNotice, onPaid }) {
  const plans = useResource(() => api(`/plans?_=${Date.now()}`, { cache: "no-store" }), []);
  const methods = useResource(() => api(`/payment-methods?_=${Date.now()}`, { cache: "no-store" }), []);
  const [plan, setPlan] = useState("");
  const [method, setMethod] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!plan && plans.data[0]?.key) setPlan(plans.data[0].key);
  }, [plans.data, plan]);

  useEffect(() => {
    if (!method && methods.data[0]) setMethod(methods.data[0]);
  }, [methods.data, method]);

  async function pay() {
    if (!plan || !method || busy) return;
    setBusy(true);
    try {
      const endpoint = method === "crypto"
        ? "/topup/crypto"
        : method === "stars"
          ? "/topup/stars"
          : method === "lava"
            ? "/topup/lava"
            : "/topup/tbank";
      const result = await api(endpoint, {
        method: "POST",
        body: JSON.stringify({ plan_key: plan }),
      });
      const url = result.invoice_link || result.pay_url;
      if (!url) throw new Error("Платёжная ссылка не получена");
      openExternal(url);
      onPaid?.();
      onClose();
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось открыть оплату" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="cxModalBackdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="cxTopupModal" role="dialog" aria-modal="true" aria-label="Пополнение баланса">
        <span className="cxTopupModal__handle"/>
        <button className="cxTopupModal__close" type="button" onClick={onClose} aria-label="Закрыть"><Icon name="close" size={24}/></button>
        <header>
          <span><Icon name="sparkle" size={17}/></span>
          <h2>Баланс</h2>
          <p>Пополняй баланс и создавай без границ</p>
        </header>

        <article className="cxCurrentBalance">
          <div><small>Текущий баланс</small><b>{formatCredits(user?.credits)}</b><span>токенов</span></div>
          <div className="cxCurrentBalance__coins"><i/><i/><i><Icon name="sparkle" size={24}/></i></div>
        </article>

        <section className="cxPlanSection">
          <h3>Выбери пакет</h3>
          {plans.loading ? <Loading label="Загружаем пакеты"/> : (
            <div className="cxPlanGrid">
              {plans.data.map((item, index) => (
                <button key={item.key} type="button" className={plan === item.key ? "active" : ""} onClick={() => setPlan(item.key)}>
                  {index === 0 && <em>Популярно</em>}
                  <b>{formatCredits(item.credits)} <Icon name="sparkle" size={13}/></b>
                  <span>токенов</span>
                  <strong>{item.price_rub_display || `${item.price_rub || 0} ₽`}</strong>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="cxPaymentSection">
          <h3>Способ оплаты</h3>
          <div>
            {methods.data.map((item) => (
              <button key={item} type="button" className={method === item ? "active" : ""} onClick={() => setMethod(item)}>
                <Icon name={item === "stars" ? "sparkle" : item === "crypto" ? "wallet" : "credit"} size={18}/>
                {item === "tbank" ? "Карта" : item === "stars" ? "Stars" : item === "crypto" ? "Крипто" : "Lava"}
              </button>
            ))}
          </div>
        </section>

        <button className="cxGenerateButton" type="button" onClick={pay} disabled={!plan || !method || busy}>
          <span>{busy ? "Открываем..." : "Пополнить"}</span><i><Icon name="sparkle" size={18}/></i>
        </button>
        <p className="cxSafePayment"><Icon name="check" size={15}/>Безопасная оплата</p>
      </section>
    </div>
  );
}
