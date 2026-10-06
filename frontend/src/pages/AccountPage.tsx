// 改自己的密码。改了之后，其他电脑上的登录都要重新登录（这一台不用）。

import { useState, type FormEvent } from "react";
import * as api from "../api";
import { useUser } from "../auth";
import { ErrorBox } from "../components";
import { useAction } from "../hooks";

const MIN_PASSWORD = 8; // = backend/app/auth.py MIN_PASSWORD_LENGTH

export default function AccountPage() {
  const me = useUser();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [done, setDone] = useState(false);
  const action = useAction();
  const mismatch = again !== "" && next !== again;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setDone(false);
    if (mismatch) return;
    const ok = await action.run(() => api.auth.changePassword(current, next));
    setCurrent("");
    if (ok) {
      setNext("");
      setAgain("");
      setDone(true);
    }
  }

  return (
    <div className="page narrow">
      <h1>My account</h1>
      <p>
        {me.name} · <span className="muted">{me.username} ({me.role})</span>
      </p>
      <form className="card inline-form" onSubmit={submit}>
        <h3>Change password</h3>
        <label>
          Current password
          <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
        </label>
        <label>
          New password (at least {MIN_PASSWORD} characters)
          <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" minLength={MIN_PASSWORD} required />
        </label>
        <label>
          New password again
          <input type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
        </label>
        {mismatch && <div className="error" role="alert">The new passwords are not the same.</div>}
        <ErrorBox message={action.error} />
        {done && <p className="ok">Password changed. Other computers where you were logged in need to log in again.</p>}
        <button type="submit" className="primary" disabled={action.busy || mismatch}>Change password</button>
      </form>
    </div>
  );
}
