import { useEffect, useRef, useState } from "react";
import { Bot, Send, Sparkles } from "lucide-react";
import type { AssistantMessage } from "@/lib/types";

export function LilacAssistant({ messages, busy, onSend }: { messages: AssistantMessage[]; busy: boolean; onSend: (text: string) => void }) {
  const [text, setText] = useState("");
  const last = useRef<HTMLDivElement>(null);
  useEffect(() => { last.current?.scrollIntoView({ block: "nearest" }); }, [messages.length]);
  const send = () => { if (!text.trim() || busy) return; onSend(text.trim()); setText(""); };
  return <div className="lilac-page lilac-chat"><header className="lilac-title"><p>Помощь с идеями и текстами</p><h1>AI-помощник</h1><span>Опишите задачу обычными словами.</span></header>
    <div className="lilac-chat-messages" role="log" aria-live="polite" aria-label="Диалог с помощником">{messages.length ? messages.map((message, index) => <div key={index} className={`lilac-message lilac-message-${message.role}`}><small>{message.role === "user" ? "Вы" : "APIX"}</small><p>{message.text}</p></div>) : <div className="lilac-empty"><Bot size={36} /><h2>С чего начнём?</h2><p>Помогу придумать идею, написать текст или составить задание для генерации.</p></div>}{busy && <p role="status">APIX готовит ответ…</p>}<div ref={last} /></div>
    {!messages.length && <div className="lilac-chat-suggestions">{["Придумай идею для фото", "Помоги написать пост", "Как оживить фотографию?"].map(value => <button key={value} onClick={() => setText(value)}><Sparkles size={15} />{value}</button>)}</div>}
    <form className="lilac-chat-composer" onSubmit={e => { e.preventDefault(); send(); }}><textarea aria-label="Сообщение помощнику" placeholder="Спросите о чём угодно" maxLength={4000} value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }} /><button type="submit" aria-label="Отправить" disabled={busy || !text.trim()}><Send size={21} /></button></form>
    <p className="lilac-note">Помощник может ошибаться. Важные факты проверяйте.</p>
  </div>;
}
