import { useState, type FormEvent } from "react";
import { useAuth } from "../auth";
import { APP_NAME, ErrorBox, PasswordInput, usePageTitle } from "../components";
import { useAction } from "../hooks";
import { ToothIcon } from "../icons";

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const action = useAction();
  usePageTitle("Log in");

  async function submit(e: FormEvent) {
    e.preventDefault();
    const ok = await action.run(() => login(username, password));
    if (!ok) setPassword(""); // 密码错了就清掉，不留在画面上
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={submit}>
        <div className="login-brand">
          <span className="brand-mark">
            <ToothIcon size={22} />
          </span>
          <div>
            <h1>{APP_NAME}</h1>
            <p className="muted">Log in to see today's reminders.</p>
          </div>
        </div>
        <label>
          Username
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
            required
          />
        </label>
        <PasswordInput
          label="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />
        <ErrorBox message={action.error} />
        <button type="submit" className="primary block" disabled={action.busy}>
          {action.busy ? "Logging in…" : "Log in"}
        </button>
      </form>
      <p className="login-foot muted">For clinic staff only. Forgot your password? Ask the admin to reset it.</p>
    </div>
  );
}
