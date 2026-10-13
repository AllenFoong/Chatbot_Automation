// 画面的外框：没登录 → 登录画面；登录了 → 左边的选单 + 各个页面。
// 选单里的 Staff accounts 只有 ADMIN 看得到。注意：这只是方便，真正挡住的是后端（STAFF 呼叫会得到 403）。
// 打开网页先到 Reminders：现在员工每天用的是提醒名单（D65）；对话、预约请求要等 5c、AI 才有资料。

import { useEffect } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router";
import * as api from "./api";
import { useAuth, useUser } from "./auth";
import { APP_NAME, Avatar, ErrorBox, Loading, PageHeader } from "./components";
import { useLoad } from "./hooks";
import { BellIcon, ChatIcon, ClipboardIcon, LogOutIcon, SlidersIcon, ToothIcon, UsersIcon } from "./icons";
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

function Layout() {
  const user = useUser();
  const { isAdmin, logout } = useAuth();
  const counts = useCounts();

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <ToothIcon size={20} />
          </span>
          <span className="brand-text">
            <span className="brand-name">{APP_NAME}</span>
            <span className="brand-sub">Front desk</span>
          </span>
        </div>
        <nav className="nav" aria-label="Main">
          <span className="nav-label">Daily work</span>
          <NavLink to="/reminders">
            <BellIcon />
            Reminders
          </NavLink>
          <NavLink to="/conversations">
            <ChatIcon />
            Conversations {counts && counts.human > 0 && <span className="count">{counts.human}</span>}
          </NavLink>
          <NavLink to="/requests">
            <ClipboardIcon />
            Requests {counts && counts.pending > 0 && <span className="count">{counts.pending}</span>}
          </NavLink>
          <span className="nav-label">Clinic setup</span>
          <NavLink to="/settings">
            <SlidersIcon />
            Settings
          </NavLink>
          {isAdmin && (
            <NavLink to="/staff">
              <UsersIcon />
              Staff accounts
            </NavLink>
          )}
        </nav>
        <div className="sidebar-footer">
          <NavLink to="/account" className="user-chip" title="My account">
            <Avatar name={user.name} />
            <span className="user-text">
              <span className="user-name">{user.name}</span>
              <span className="user-role">{user.role === "ADMIN" ? "Admin" : "Staff"} · My account</span>
            </span>
          </NavLink>
          <button type="button" className="logout" onClick={() => void logout()}>
            <LogOutIcon />
            Log out
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
