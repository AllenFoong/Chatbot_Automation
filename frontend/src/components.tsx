// 小的共用画面元件。底下用 shadcn/ui（src/components/ui/，D83）；这里的名字、参数和以前一样，页面不用改写法。

import { useEffect, useId, useState, type FormEvent, type InputHTMLAttributes, type ReactNode } from "react";
import { CheckIcon, EyeIcon, EyeOffIcon, InboxIcon, InfoIcon, LoaderCircleIcon, TriangleAlertIcon } from "lucide-react";
import { Alert, AlertDescription } from "./components/ui/alert";
import { Avatar as AvatarCircle } from "./components/ui/avatar";
import { Badge as UiBadge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./components/ui/dialog";
import { Input } from "./components/ui/input";
import { Label } from "./components/ui/label";
import { Switch as UiSwitch } from "./components/ui/switch";
import { cn } from "./lib/utils";

export const APP_NAME = "Clinic Admin";

/** 浏览器分页的名字：「Reminders · Clinic Admin」 */
export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = `${title} · ${APP_NAME}`;
  }, [title]);
}

/** 每页最外面一层：最宽 1180px、置中，里面的东西上下有间隔 */
export function Page({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mx-auto flex w-full max-w-[1180px] flex-col gap-5", className)}>{children}</div>;
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
    <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <div className="max-w-[80ch] text-sm text-muted-foreground">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-end gap-2">{actions}</div>}
    </header>
  );
}

type Tone = "info" | "warning" | "success" | "neutral";

const TONE_ICON: Record<Tone, ReactNode> = {
  info: <InfoIcon />,
  warning: <TriangleAlertIcon />,
  success: <CheckIcon />,
  neutral: <InfoIcon />,
};

/** 一段提醒（黄色 = 要注意，蓝色 = 说明，绿色 = 完成）。不是错误：读屏软件不会马上念（role=status） */
export function Notice({ tone = "info", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <Alert variant={tone} role="status">
      {TONE_ICON[tone]}
      <AlertDescription className="block">{children}</AlertDescription>
    </Alert>
  );
}

/** 出错（role=alert）；onRetry 给了就多一个 Try again */
export function ErrorBox({ message, onRetry }: { message: string | null; onRetry?: () => void }) {
  if (!message) return null;
  return (
    <Alert variant="destructive">
      <TriangleAlertIcon />
      <AlertDescription className="flex flex-wrap items-center gap-x-3">
        <span>{message}</span>
        {onRetry && (
          <Button type="button" variant="link" size="sm" onClick={onRetry}>
            Try again
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}

export function Loading() {
  return (
    <p className="flex items-center gap-2 text-sm text-muted-foreground">
      <LoaderCircleIcon className="size-4 animate-spin" aria-hidden="true" />
      Loading…
    </p>
  );
}

type BadgeVariant = "success" | "warning" | "destructive" | "info" | "secondary" | "brand";

/** 状态 → 颜色：绿 = 好了，黄 = 等人处理，红 = 拒绝，蓝 = AI，灰 = 结束 / 没用，青绿 = 员工的身分 */
const BADGE_VARIANT: Record<string, BadgeVariant> = {
  ok: "success",
  confirmed: "success",
  pending: "warning",
  human: "warning",
  rejected: "destructive",
  bot: "info",
  closed: "secondary",
  cancelled: "secondary",
  idle: "secondary",
  admin: "brand",
  staff: "brand",
};

export function Badge({ kind, children }: { kind: string; children: ReactNode }) {
  return <UiBadge variant={BADGE_VARIANT[kind.toLowerCase()] ?? "secondary"}>{children}</UiBadge>;
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed bg-card px-6 py-12 text-center text-sm text-muted-foreground">
      <InboxIcon className="size-7 text-subtle" aria-hidden="true" />
      <p>{children}</p>
    </div>
  );
}

/** 名字的第一个字母（选单下面、对话列表的圆形） */
export function Avatar({ name, className }: { name: string; className?: string }) {
  const letters = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
  return (
    <AvatarCircle aria-hidden="true" className={className}>
      {letters || "?"}
    </AvatarCircle>
  );
}

/** 一排切换的按钮（例如 Pending / Confirmed / …）；count 显示在名字后面的小圆框里。样子和 shadcn 的 Tabs 一样 */
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
    <div
      role="tablist"
      aria-label={label}
      className="inline-flex h-10 w-fit max-w-full items-center overflow-x-auto rounded-lg bg-secondary p-1 text-muted-foreground"
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="tab"
            aria-selected={active}
            data-slot="tabs-trigger"
            data-state={active ? "active" : "inactive"}
            className="inline-flex h-full cursor-pointer items-center justify-center gap-1.5 rounded-md px-3 text-sm font-medium whitespace-nowrap transition-[color,box-shadow] outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/30 data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm"
            onClick={() => onChange(o.value)}
          >
            {o.label}
            {o.count !== undefined && (
              <>
                {" "}
                <UiBadge variant="secondary" className="min-w-5 rounded-full px-1.5 tabular-nums">
                  {o.count}
                </UiBadge>
              </>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** 密码栏：右边的眼睛按一下看得到打的字，再按一下藏起来（只在这台电脑的画面上，不会送出去）。
 *  label 给了就自己画标题（眼睛按钮在 <label> 外面，读屏软件才不会把密码栏念成「Password Show password」）；
 *  没有标题的（例：重设密码那一栏）用 aria-label。 */
export function PasswordInput({
  label,
  className,
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { label?: ReactNode }) {
  const [shown, setShown] = useState(false);
  const id = useId();
  const field = (
    <span className={cn("relative block w-full", className)}>
      <Input {...props} id={props.id ?? id} type={shown ? "text" : "password"} className="pr-10" />
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="absolute top-0 right-0 size-9 text-muted-foreground hover:bg-transparent hover:text-foreground"
        aria-label={shown ? "Hide password" : "Show password"}
        aria-pressed={shown}
        title={shown ? "Hide password" : "Show password"}
        onClick={() => setShown((v) => !v)}
      >
        {shown ? <EyeOffIcon /> : <EyeIcon />}
      </Button>
    </span>
  );
  if (label === undefined) return field;
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={props.id ?? id} className="leading-5 text-text-2">
        {label}
      </Label>
      {field}
    </div>
  );
}

/** On / off 开关（开是青绿色、关是灰色），照 iOS 设定的排法：名字在左边，开关在右边。
 *  shadcn 的 Switch（读屏软件念成 switch）；旁边的 On / Off 只是给眼睛看的。 */
export function Switch({
  label,
  checked,
  disabled = false,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  const id = useId();
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-4 rounded-lg border bg-card px-4 py-3",
        disabled && "opacity-70",
      )}
    >
      <Label htmlFor={id} className="leading-snug font-medium">
        {label}
      </Label>
      <span className="flex items-center gap-2">
        <UiSwitch id={id} checked={checked} disabled={disabled} onCheckedChange={onChange} />
        <span
          aria-hidden="true"
          className={cn("w-7 text-sm font-medium", checked ? "text-primary" : "text-muted-foreground")}
        >
          {checked ? "On" : "Off"}
        </span>
      </span>
    </div>
  );
}

/** 画面中间的弹出视窗（shadcn 的 Dialog）。后面的页面变暗、不跟着卷动；内容长的话视窗里面上下拉。
 *  Esc、点视窗外面、右上角 × 都是关掉（busy 的时候不能关）。onSubmit 给了，整个视窗是一个 form。 */
export function Modal({
  title,
  subtitle,
  busy = false,
  onClose,
  onSubmit,
  footer,
  children,
}: {
  title: string;
  subtitle?: ReactNode;
  busy?: boolean;
  onClose: () => void;
  onSubmit?: (e: FormEvent) => void;
  footer: ReactNode;
  children: ReactNode;
}) {
  const body = (
    <>
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        {subtitle && <DialogDescription>{subtitle}</DialogDescription>}
      </DialogHeader>
      <div className="flex min-w-0 flex-col gap-4">{children}</div>
      <DialogFooter className="flex-wrap">{footer}</DialogFooter>
    </>
  );
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <DialogContent
        className="sm:max-w-xl"
        {...(subtitle ? {} : { "aria-describedby": undefined })}
        onEscapeKeyDown={(e) => busy && e.preventDefault()}
        onInteractOutside={(e) => busy && e.preventDefault()}
      >
        {onSubmit ? (
          <form className="flex flex-col gap-5" onSubmit={onSubmit}>
            {body}
          </form>
        ) : (
          <div className="flex flex-col gap-5">{body}</div>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** 卡片的标题和一句说明（设置页的每一块、员工账号、我的账号） */
export function SectionTitle({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <h3 className="text-base font-semibold">{title}</h3>
      {children && <div className="max-w-[80ch] text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}

/** 表单的一栏：<label> 包住标题和输入框（和以前一样，测试用 getByLabelText 找得到），下面可以有一句说明 */
export function Field({
  label,
  help,
  className,
  children,
}: {
  label: ReactNode;
  help?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <label className="flex flex-col gap-1.5 text-sm font-medium text-text-2">
        {label}
        {children}
      </label>
      {help && <p className="text-xs text-muted-foreground">{help}</p>}
    </div>
  );
}
