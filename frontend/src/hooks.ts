// 画面共用的两个 hook：
// - useLoad：读资料（显示 loading、错误、可以重新读；可以每隔几秒自动更新）
// - useAction：按钮做事情（做的时候按钮不能再按，失败显示错误）

import { useCallback, useEffect, useRef, useState } from "react";

export function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export interface Loaded<T> {
  data: T | undefined;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/**
 * 读资料。deps 改变时重新读。
 * refreshMs：每隔多久自动更新（例如对话列表）；浏览器分页没在看的时候不更新。
 */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[], refreshMs?: number): Loaded<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    let alive = true; // 换页或 deps 改变后，旧的回应不要盖掉新的
    setLoading(true);
    loadRef.current().then(
      (result) => {
        if (!alive) return;
        setData(result);
        setError(null);
        setLoading(false);
      },
      (e: unknown) => {
        if (!alive) return;
        setError(messageOf(e));
        setLoading(false);
      },
    );
    return () => {
      alive = false;
    };
  }, [...deps, version]);

  // deps 改变时，旧的资料不能留着（例如换了一段对话）
  const depsKey = JSON.stringify(deps);
  const lastKey = useRef(depsKey);
  if (lastKey.current !== depsKey) {
    lastKey.current = depsKey;
    setData(undefined);
  }

  const reload = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    if (!refreshMs) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") reload();
    }, refreshMs);
    return () => window.clearInterval(timer);
  }, [refreshMs, reload]);

  return { data, error, loading, reload };
}

export interface Action {
  busy: boolean;
  error: string | null;
  run: (action: () => Promise<unknown>) => Promise<boolean>;
  clearError: () => void;
}

export function useAction(): Action {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      return true;
    } catch (e) {
      setError(messageOf(e));
      return false;
    } finally {
      setBusy(false);
    }
  }, []);

  return { busy, error, run, clearError: useCallback(() => setError(null), []) };
}
