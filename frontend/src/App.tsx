// 画面的外框：没登录 → 登录画面；登录了 → 左边的选单 + 各个页面。
// 选单里的 Staff accounts 只有 ADMIN 看得到。注意：这只是方便，真正挡住的是后端（STAFF 呼叫会得到 403）。
// 打开网页先到 Reminders：现在员工每天用的是提醒名单（D65）；对话、预约请求要等 5c、AI 才有资料。
// 选单的 ☰（hamburger）：
// - 电脑萤幕：选单左上角的 ☰ 把选单收成只有图示（内容比较宽），再按一次展开；这台电脑记住（localStorage）。
// - 窄的萤幕（平板、手机）：上面一排的 ☰ 打开选单（从左边滑出来）；按旁边、按 Esc、选了页面就关。

import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router";
import * as api from "./api";
import { useAuth, useUser } from "./auth";
import { APP_NAME, Avatar, ErrorBox, Loading, Page, PageHeader } from "./components";
import { Button } from "./components/ui/button";
import { cn } from "./lib/utils";
import { useLoad } from "./hooks";
import {
  BellIcon,
  ChatIcon,
  ClipboardIcon,
  CloseIcon,
  LogOutIcon,
  MenuIcon,
  SlidersIcon,
  ToothIcon,
  UsersIcon,
} from "./icons";
import AccountPage from "./pages/AccountPage";
import ConversationsPage from "./pages/ConversationsPage";
import LoginPage from "./pages/LoginPage";
import RemindersPage from "./pages/RemindersPage";
import RequestsPage from "./pages/RequestsPage";
import SettingsPage from "./pages/SettingsPage";
import StaffPage from "./pages/StaffPage";

/** 选单上的数字：要员工处理的对话、待确认 + 要通知病人的请求。每 30 秒更新；员工改了资料（例如接手）也马上更新。 */
function useCounts() {
  const { data, reload } = useLoad(
    async () => {
      const [human, pending, toTell] = await Promise.all([
        api.conversations.list("HUMAN"),
        api.requests.list("PENDING"),
        api.requests.toTell(),
      ]);
      return { human: human.length, pending: pending.length + toTell.length };
    },
    [],
    30_000,
  );
  useEffect(() => {
    window.addEventListener(api.DATA_CHANGED, reload);
    return () => window.removeEventListener(api.DATA_CHANGED, reload);
  }, [reload]);
  return data;
}

const COLLAPSED_KEY = "clinicAdmin.menuCollapsed";

/** 收起选单的选择存在这台电脑的浏览器；读不到（无痕视窗等）就当作没收起 */
function loadCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

function saveCollapsed(collapsed: boolean) {
  try {
    localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
  } catch {
    // 存不了也没关系：下次打开是展开的
  }
}

const navLink =
  "group relative flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium text-text-2 no-underline transition-colors outline-none hover:bg-muted hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/30 aria-[current=page]:bg-brand-soft aria-[current=page]:text-brand-text [&_svg]:shrink-0 [&_svg]:text-muted-foreground aria-[current=page]:[&_svg]:text-brand-text";

/** 选单的一项。收起时只看到图示：名字留给读屏软件，滑过显示名字（title） */
function NavItem({ to, icon, label, count, collapsed }: {
  to: string;
  icon: ReactNode;
  label: string;
  count?: number;
  collapsed: boolean;
}) {
  return (
    <NavLink to={to} title={collapsed ? label : undefined} className={cn(navLink, collapsed && "min-[861px]:justify-center min-[861px]:px-0")}>
      {icon}
      <span className={cn("flex-1 truncate", collapsed && "min-[861px]:sr-only")}>{label}</span>{" "}
      {count !== undefined && count > 0 && (
        <span
          className={cn(
            "inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1.5 text-xs font-semibold text-white tabular-nums",
            collapsed && "min-[861px]:absolute min-[861px]:top-0.5 min-[861px]:right-1.5 min-[861px]:h-4 min-[861px]:min-w-4 min-[861px]:px-1 min-[861px]:text-[10px]",
          )}
        >
          {count}
        </span>
      )}
    </NavLink>
  );
}

function NavLabel({ children, collapsed }: { children: ReactNode; collapsed: boolean }) {
  return (
    <span
      className={cn(
        "px-3 pt-4 pb-1 text-[11px] font-semibold tracking-wider text-subtle uppercase",
        collapsed && "min-[861px]:sr-only",
      )}
    >
      {children}
    </span>
  );
}

function BrandMark({ size = 20, className }: { size?: number; className?: string }) {
  return (
    <span
      className={cn(
        "flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground",
        className,
      )}
    >
      <ToothIcon size={size} />
    </span>
  );
}

function Layout() {
  const user = useUser();
  const { isAdmin, logout } = useAuth();
  const counts = useCounts();
  const [collapsed, setCollapsed] = useState(loadCollapsed); // 电脑萤幕：选单只有图示
  const [open, setOpen] = useState(false); // 窄的萤幕：选单打开了
  const { pathname } = useLocation();
  const openButton = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);

  // 选了页面就关
  useEffect(() => setOpen(false), [pathname]);

  // 打开时焦点移到「关」，按 Esc 关掉、焦点回到 ☰（用键盘的人不会迷路）
  useEffect(() => {
    if (!open) return;
    closeButton.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        openButton.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  function toggleCollapsed() {
    setCollapsed((c) => {
      saveCollapsed(!c);
      return !c;
    });
  }

  return (
    <div
      className={cn(
        "grid min-h-screen bg-background max-[860px]:grid-rows-[auto_1fr]",
        collapsed ? "min-[861px]:grid-cols-[72px_minmax(0,1fr)]" : "min-[861px]:grid-cols-[236px_minmax(0,1fr)]",
      )}
    >
      {/* 窄的萤幕才有：上面一排的 ☰ */}
      <header className="sticky top-0 z-20 flex h-14 items-center gap-2.5 border-b bg-card px-3 min-[861px]:hidden">
        <Button
          ref={openButton}
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Open menu"
          aria-expanded={open}
          aria-controls="main-menu"
          onClick={() => setOpen(true)}
        >
          <MenuIcon />
        </Button>
        <BrandMark size={16} className="size-7 rounded-md" />
        <span className="font-semibold">{APP_NAME}</span>
      </header>
      {open && (
        <div aria-hidden="true" className="fixed inset-0 z-30 bg-black/40 min-[861px]:hidden" onClick={() => setOpen(false)} />
      )}
      {/* 电脑萤幕：外面这一栏一直是白色到底（页面很长也一样），里面的选单固定在画面上；窄的萤幕：这一层不算（contents） */}
      <div className="border-r bg-card max-[860px]:contents">
      <aside
        id="main-menu"
        className={cn(
          "flex flex-col gap-1 overflow-x-hidden overflow-y-auto bg-card px-3 pt-4 pb-3 max-[860px]:border-r",
          "min-[861px]:sticky min-[861px]:top-0 min-[861px]:h-screen",
          "max-[860px]:fixed max-[860px]:inset-y-0 max-[860px]:left-0 max-[860px]:z-40 max-[860px]:w-[min(280px,85vw)] max-[860px]:shadow-lg max-[860px]:transition-[translate,visibility] max-[860px]:duration-200",
          open ? "max-[860px]:visible max-[860px]:translate-x-0" : "max-[860px]:invisible max-[860px]:-translate-x-full",
        )}
      >
        <div className={cn("flex items-center justify-between gap-2 pb-2", collapsed && "min-[861px]:flex-col")}>
          <div className={cn("flex min-w-0 items-center gap-2.5", collapsed && "min-[861px]:hidden")}>
            <BrandMark />
            <span className="flex min-w-0 flex-col leading-tight">
              <span className="truncate font-semibold">{APP_NAME}</span>
              <span className="text-xs text-muted-foreground">Front desk</span>
            </span>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="text-muted-foreground max-[860px]:hidden"
            aria-label={collapsed ? "Expand menu" : "Collapse menu"}
            title={collapsed ? "Expand menu" : "Collapse menu"}
            aria-expanded={!collapsed}
            aria-controls="main-menu"
            onClick={toggleCollapsed}
          >
            <MenuIcon />
          </Button>
          <Button
            ref={closeButton}
            type="button"
            variant="ghost"
            size="icon"
            className="text-muted-foreground min-[861px]:hidden"
            aria-label="Close menu"
            onClick={() => setOpen(false)}
          >
            <CloseIcon />
          </Button>
        </div>
        <nav className="flex flex-col gap-0.5" aria-label="Main">
          <NavLabel collapsed={collapsed}>Daily work</NavLabel>
          <NavItem to="/reminders" icon={<BellIcon />} label="Reminders" collapsed={collapsed} />
          <NavItem to="/conversations" icon={<ChatIcon />} label="Conversations" count={counts?.human} collapsed={collapsed} />
          <NavItem to="/requests" icon={<ClipboardIcon />} label="Requests" count={counts?.pending} collapsed={collapsed} />
          <NavLabel collapsed={collapsed}>Clinic setup</NavLabel>
          <NavItem to="/settings" icon={<SlidersIcon />} label="Settings" collapsed={collapsed} />
          {isAdmin && <NavItem to="/staff" icon={<UsersIcon />} label="Staff accounts" collapsed={collapsed} />}
        </nav>
        <div className="mt-auto flex flex-col gap-1 border-t pt-3">
          <NavLink
            to="/account"
            title="My account"
            className={cn(navLink, "h-auto py-2", collapsed && "min-[861px]:justify-center min-[861px]:px-0")}
          >
            <Avatar name={user.name} />
            <span className={cn("flex min-w-0 flex-col leading-tight", collapsed && "min-[861px]:sr-only")}>
              <span className="truncate text-foreground">{user.name}</span>{" "}
              <span className="text-xs font-normal text-muted-foreground">
                {user.role === "ADMIN" ? "Admin" : "Staff"} · My account
              </span>
            </span>
          </NavLink>
          <button
            type="button"
            title={collapsed ? "Log out" : undefined}
            className={cn(navLink, "w-full cursor-pointer", collapsed && "min-[861px]:justify-center min-[861px]:px-0")}
            onClick={() => void logout()}
          >
            <LogOutIcon />
            <span className={cn(collapsed && "min-[861px]:sr-only")}>Log out</span>
          </button>
        </div>
      </aside>
      </div>
      <main className="min-w-0 px-4 py-4 min-[861px]:px-6 min-[861px]:pt-7 min-[861px]:pb-12 min-[1101px]:px-9">
        <Routes>
          <Route path="/" element={<Navigate to="/reminders" replace />} />
          <Route path="/conversations" element={<ConversationsPage />} />
          <Route path="/conversations/:id" element={<ConversationsPage />} />
          <Route path="/requests" element={<RequestsPage />} />
          <Route path="/reminders" element={<RemindersPage />} />
          <Route path="/settings" element={<Navigate to="/settings/doctors" replace />} />
          <Route path="/settings/:section" element={<SettingsPage />} />
          <Route path="/staff" element={isAdmin ? <StaffPage /> : <Navigate to="/" replace />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  );
}

function NotFound() {
  return (
    <Page>
      <PageHeader title="Page not found" description="This address does not exist in Clinic Admin." />
      <p>
        <NavLink to="/reminders" className="text-brand-text underline underline-offset-2">
          Go to Reminders
        </NavLink>
      </p>
    </Page>
  );
}

export default function App() {
  const { user, error, retry } = useAuth();
  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4">
        <ErrorBox message={error} onRetry={retry} />
      </div>
    );
  }
  if (user === undefined) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4">
        <Loading />
      </div>
    );
  }
  return user ? <Layout /> : <LoginPage />;
}
