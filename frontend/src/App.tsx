// 画面的外框：没登录 → 登录画面；登录了 → 上面一排选单 + 各个页面。
// 选单里的 Staff accounts 只有 ADMIN 看得到。注意：这只是方便，真正挡住的是后端（STAFF 呼叫会得到 403）。

import { useEffect } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router";
import * as api from "./api";
import { useAuth, useUser } from "./auth";
import { ErrorBox, Loading } from "./components";
import { useLoad } from "./hooks";
import AccountPage from "./pages/AccountPage";
import ConversationsPage from "./pages/ConversationsPage";
import LoginPage from "./pages/LoginPage";
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
      <header className="topbar">
        <span className="brand">Clinic Admin</span>
        <nav aria-label="Main">
          <NavLink to="/conversations">
            Conversations {counts && counts.human > 0 && <span className="count">{counts.human}</span>}
          </NavLink>
          <NavLink to="/requests">
            Requests {counts && counts.pending > 0 && <span className="count">{counts.pending}</span>}
          </NavLink>
          <NavLink to="/settings">Settings</NavLink>
          {isAdmin && <NavLink to="/staff">Staff accounts</NavLink>}
        </nav>
        <div className="who">
          <NavLink to="/account" title="My account">
            {user.name} <span className="muted">({user.role})</span>
          </NavLink>
          <button type="button" onClick={() => void logout()}>
            Log out
          </button>
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/conversations" replace />} />
          <Route path="/conversations" element={<ConversationsPage />} />
          <Route path="/conversations/:id" element={<ConversationsPage />} />
          <Route path="/requests" element={<RequestsPage />} />
          <Route path="/settings" element={<Navigate to="/settings/doctors" replace />} />
          <Route path="/settings/:section" element={<SettingsPage />} />
          <Route path="/staff" element={isAdmin ? <StaffPage /> : <Navigate to="/" replace />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
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
