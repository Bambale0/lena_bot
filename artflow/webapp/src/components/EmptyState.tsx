type Props = {
  title: string;
  text?: string;
  action?: string;
  onAction?: () => void;
};

export function EmptyState({ title, text, action, onAction }: Props) {
  return (
    <div className="empty">
      <div className="emptyIcon">✦</div>
      <h3>{title}</h3>
      {text ? <p>{text}</p> : null}
      {action && onAction ? <button onClick={onAction}>{action}</button> : null}
    </div>
  );
}
