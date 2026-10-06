import { useState, type FormEvent } from "react";
import { useAuth } from "../auth";
import { ErrorBox } from "../components";
import { useAction } from "../hooks";

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const action = useAction();

  async function submit(e: FormEvent) {
    e.preventDefault();
    const ok = await action.run(() => login(username, password));
    if (!ok) setPassword(""); // 密码错了就清掉，不留在画面上
  }

  return (
    <div className="center">
      <form className="card login" onSubmit={submit}>
        <h1>Clinic Admin</h1>
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
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        <ErrorBox message={action.error} />
        <button type="submit" className="primary" disabled={action.busy}>
          {action.busy ? "Logging in…" : "Log in"}
        </button>
      </form>
    </div>
  );
}
