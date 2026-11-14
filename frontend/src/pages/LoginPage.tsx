import { useState, type FormEvent } from "react";
import { useAuth } from "../auth";
import { APP_NAME, ErrorBox, Field, PasswordInput, usePageTitle } from "../components";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { Input } from "../components/ui/input";
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
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background px-4 py-10">
      <Card className="w-full max-w-sm gap-6 py-7 shadow-lg">
        <CardHeader className="flex items-center gap-3 px-7">
          <span className="flex size-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <ToothIcon size={22} />
          </span>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{APP_NAME}</h1>
            <p className="text-sm text-muted-foreground">Log in to see today's reminders.</p>
          </div>
        </CardHeader>
        <CardContent className="px-7">
          <form className="flex flex-col gap-4" onSubmit={submit}>
            <Field label="Username">
              <Input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                required
              />
            </Field>
            <PasswordInput
              label="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
            <ErrorBox message={action.error} />
            <Button type="submit" className="w-full" disabled={action.busy}>
              {action.busy ? "Logging in…" : "Log in"}
            </Button>
          </form>
        </CardContent>
      </Card>
      <p className="text-center text-xs text-muted-foreground">
        For clinic staff only. Forgot your password? Ask the admin to reset it.
      </p>
    </div>
  );
}
