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
import { APP_NAME, Avatar, ErrorBox, Loading, PageHeader } from "./components";
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

/** 选单上的数字：要员工处理的对话、待确认的请求。每 30 秒更新；员工改了资料（例如接手）也马上更新。 */
function useCounts() {
  const { data, reload } = useLoad(
    async () => {
      const [human, pending] = await Promise.all([api.conversations.list("HUMAN"), api.requests.list("PENDING")]);
      return { human: human.length, pending: pending.length };
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

/** 选单的一项。收起时只看到图示：名字留给读屏软件，滑过显示名字（title） */
function NavItem({ to, icon, label, count, collapsed }: {
  to: string;
  icon: ReactNode;
  label: string;
  count?: number;
  collapsed: boolean;
}) {
  return (
    <NavLink to={to} title={collapsed ? label : undefined}>
      {icon}
      <span className="nav-text">{label}</span> {count !== undefined && count > 0 && <span className="count">{count}</span>}
    </NavLink>
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

  const appClass = ["app", collapsed ? "menu-collapsed" : "", open ? "menu-open" : ""].filter(Boolean).join(" ");

  return (
    <div className={appClass}>
      <header className="topbar">
        <button
          ref={openButton}
          type="button"
          className="ghost icon-button"
          aria-label="Open menu"
          aria-expanded={open}
          aria-controls="main-menu"
          onClick={() => setOpen(true)}
        >
          <MenuIcon />
        </button>
        <span className="brand-mark small">
          <ToothIcon size={16} />
        </span>
        <span className="brand-name">{APP_NAME}</span>
      </header>
      {open && <div className="menu-backdrop" aria-hidden="true" onClick={() => setOpen(false)} />}
      <aside className="sidebar" id="main-menu">
        <div className="sidebar-head">
          <div className="brand">
            <span className="brand-mark">
              <ToothIcon size={20} />
            </span>
            <span className="brand-text">
              <span className="brand-name">{APP_NAME}</span>
              <span className="brand-sub">Front desk</span>
            </span>
          </div>
          <button
            type="button"
            className="ghost icon-button collapse-button"
            aria-label={collapsed ? "Expand menu" : "Collapse menu"}
            title={collapsed ? "Expand menu" : "Collapse menu"}
            aria-expanded={!collapsed}
            aria-controls="main-menu"
            onClick={toggleCollapsed}
          >
            <MenuIcon />
          </button>
          <button
            ref={closeButton}
            type="button"
            className="ghost icon-button close-button"
            aria-label="Close menu"
            onClick={() => setOpen(false)}
          >
            <CloseIcon />
          </button>
        </div>
        <nav className="nav" aria-label="Main">
          <span className="nav-label">Daily work</span>
          <NavItem to="/reminders" icon={<BellIcon />} label="Reminders" collapsed={collapsed} />
          <NavItem to="/conversations" icon={<ChatIcon />} label="Conversations" count={counts?.human} collapsed={collapsed} />
          <NavItem to="/requests" icon={<ClipboardIcon />} label="Requests" count={counts?.pending} collapsed={collapsed} />
          <span className="nav-label">Clinic setup</span>
          <NavItem to="/settings" icon={<SlidersIcon />} label="Settings" collapsed={collapsed} />
          {isAdmin && <NavItem to="/staff" icon={<UsersIcon />} label="Staff accounts" collapsed={collapsed} />}
        </nav>
        <div className="sidebar-footer">
          <NavLink to="/account" className="user-chip" title="My account">
            <Avatar name={user.name} />
            <span className="user-text">
              <span className="user-name">{user.name}</span>{" "}
              <span className="user-role">{user.role === "ADMIN" ? "Admin" : "Staff"} · My account</span>
            </span>
          </NavLink>
          <button type="button" className="logout" title={collapsed ? "Log out" : undefined} onClick={() => void logout()}>
            <LogOutIcon />
            <span className="nav-text">Log out</span>
          </button>
        </div>
      </aside>
      <main>
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
    <div className="page">
      <PageHeader title="Page not found" description="This address does not exist in Clinic Admin." />
      <p>
        <NavLink to="/reminders">Go to Reminders</NavLink>
      </p>
    </div>
  );
}

export default function App() {
  const { user, error, retry } = useAuth();
  if (error) {
    return (
      <div className="center">
        <ErrorBox message={error} onRetry={retry} />
      </div>
    );
  }
  if (user === undefined) {
    return (
      <div className="center">
        <Loading />
      </div>
    );
  }
  return user ? <Layout /> : <LoginPage />;
}
