// 小的共用画面元件。

import { useEffect, useId, useState, type InputHTMLAttributes, type ReactNode } from "react";
import { AlertIcon, CheckIcon, EyeIcon, EyeOffIcon, InboxIcon, InfoIcon } from "./icons";

export const APP_NAME = "Clinic Admin";

/** 浏览器分页的名字：「Reminders · Clinic Admin」 */
export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = `${title} · ${APP_NAME}`;
  }, [title]);
}

/** 每个画面上面的标题、一句说明、右边的按钮；浏览器分页的名字也跟着改 */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  usePageTitle(title);
  return (
    <header className="page-header">
      <div className="page-heading">
        <h1>{title}</h1>
        {description && <div className="page-description">{description}</div>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

type Tone = "info" | "warning" | "success" | "neutral";

const TONE_ICON: Record<Tone, ReactNode> = {
  info: <InfoIcon />,
  warning: <AlertIcon />,
  success: <CheckIcon />,
  neutral: <InfoIcon />,
};

/** 一段提醒（黄色 = 要注意，蓝色 = 说明，绿色 = 完成） */
export function Notice({ tone = "info", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <div className={`notice notice-${tone}`}>
      {TONE_ICON[tone]}
      <div className="notice-body">{children}</div>
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string | null; onRetry?: () => void }) {
  if (!message) return null;
  return (
    <div className="error" role="alert">
      <AlertIcon />
      <span className="error-text">{message}</span>
      {onRetry && (
        <button type="button" className="link" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function Loading() {
  return (
    <p className="loading muted">
      <span className="spinner" aria-hidden="true" />
      Loading…
    </p>
  );
}

export function Badge({ kind, children }: { kind: string; children: ReactNode }) {
  return <span className={`badge badge-${kind.toLowerCase()}`}>{children}</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="empty">
      <InboxIcon size={28} />
      <p>{children}</p>
    </div>
  );
}

/** 名字的第一个字母（选单下面、对话列表的圆形） */
export function Avatar({ name }: { name: string }) {
  const letters = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
  return (
    <span className="avatar" aria-hidden="true">
      {letters || "?"}
    </span>
  );
}

/** 一排切换的按钮（例如 Pending / Confirmed / …）；count 显示在名字后面的小圆框里 */
export function Tabs<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string; count?: number }[];
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={o.value === value}
          className={o.value === value ? "tab active" : "tab"}
          onClick={() => onChange(o.value)}
        >
          {o.label}
          {o.count !== undefined && (
            <>
              {" "}
              <span className="tab-count">{o.count}</span>
            </>
          )}
        </button>
      ))}
    </div>
  );
}

/** 密码栏：右边的眼睛按一下看得到打的字，再按一下藏起来（只在这台电脑的画面上，不会送出去）。
 *  label 给了就自己画标题（眼睛按钮在 <label> 外面，读屏软件才不会把密码栏念成「Password Show password」）；
 *  没有标题的（例：重设密码那一栏）用 aria-label。 */
export function PasswordInput({
  label,
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { label?: ReactNode }) {
  const [shown, setShown] = useState(false);
  const id = useId();
  const field = (
    <span className="password-field">
      <input {...props} id={props.id ?? id} type={shown ? "text" : "password"} />
      <button
        type="button"
        className="ghost password-eye"
        aria-label={shown ? "Hide password" : "Show password"}
        aria-pressed={shown}
        title={shown ? "Hide password" : "Show password"}
        onClick={() => setShown((v) => !v)}
      >
        {shown ? <EyeOffIcon size={16} /> : <EyeIcon size={16} />}
      </button>
    </span>
  );
  if (label === undefined) return field;
  return (
    <div className="password-label">
      <label htmlFor={props.id ?? id}>{label}</label>
      {field}
    </div>
  );
}
