import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Referrals as ReferralsType } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { Header } from "../components/Header";
import { Loading } from "../components/Loading";

type Props = {
  onProfile: () => void;
};

export function Referrals({ onProfile }: Props) {
  const [data, setData] = useState<ReferralsType | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api.getReferrals().then(setData);
  }, []);

  if (!data) return <div className="page"><Header title="Рефералы" onProfile={onProfile} /><Loading /></div>;

  const copy = async () => {
    await navigator.clipboard?.writeText(data.referral_link);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  return (
    <div className="page">
      <Header title="Рефералы" onProfile={onProfile} />
      <section className="refCard">
        <span>Код</span>
        <h1>{data.referral_code}</h1>
        <p>{data.referral_link}</p>
        <button className="primary" onClick={copy}>{copied ? "Скопировано" : "Копировать ссылку"}</button>
      </section>
      <div className="levels">
        <div><b>{data.rates.level1}%</b><span>1 линия</span><strong>{data.level1_count}</strong></div>
        <div><b>{data.rates.level2}%</b><span>2 линия</span><strong>{data.level2_count}</strong></div>
        <div><b>{data.rates.level3}%</b><span>3 линия</span><strong>{data.level3_count}</strong></div>
      </div>
      <section className="plainPanel">
        <h2>{data.earned_bananas} 🍌 заработано</h2>
        <p>Делись ссылкой: за активность приглашённых начисляются бонусы по трём уровням.</p>
      </section>
      {!data.level1_count && !data.level2_count && !data.level3_count ? <EmptyState title="Приглашений пока нет" /> : null}
    </div>
  );
}
