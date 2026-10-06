// 谁登录了。打开网页时问后端 /api/auth/me：
// - 有登录（cookie 还有效）→ 显示画面
// - 401 → 显示登录画面
// 网页本身不存任何登录资料（没有 localStorage）：cookie 是 HttpOnly，只有浏览器和后端看得到。

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, auth, setUnauthorizedHandler } from "./api";
import { messageOf } from "./hooks";
import type { StaffMember } from "./types";

interface AuthState {
  /** undefined = 还在问后端；null = 没登录 */
  user: StaffMember | null | undefined;
  /** 连不上后端等错误（不是"没登录"） */
  error: string | null;
  isAdmin: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  retry: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<StaffMember | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    auth.me().then(
      (me) => alive && setUser(me),
      (e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 401) {
          setUser(null);
        } else {
          setError(messageOf(e));
        }
      },
    );
    return () => {
      alive = false;
    };
  }, [attempt]);

  // 用到一半登录过期（12 小时）、被停用、密码被重设：任何 API 回 401 就回到登录画面
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    return () => setUnauthorizedHandler(null);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    setUser(await auth.login(username, password));
    setError(null);
  }, []);

  const logout = useCallback(async () => {
    try {
      await auth.logout();
    } finally {
      setUser(null);
    }
  }, []);

  const retry = useCallback(() => {
    setError(null);
    setUser(undefined);
    setAttempt((a) => a + 1);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user, error, isAdmin: user?.role === "ADMIN", login, logout, retry }),
    [user, error, login, logout, retry],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}

/** 已经登录的员工（只在登录后的画面里用） */
export function useUser(): StaffMember {
  const { user } = useAuth();
  if (!user) throw new Error("useUser called while logged out");
  return user;
}
