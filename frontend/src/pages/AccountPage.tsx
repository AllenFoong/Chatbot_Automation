// 改自己的密码。改了之后，其他电脑上的登录都要重新登录（这一台不用）。

import { useState, type FormEvent } from "react";
import * as api from "../api";
import { useUser } from "../auth";
import { Avatar, Badge, ErrorBox, Notice, Page, PageHeader, PasswordInput, SectionTitle } from "../components";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
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
    <Page className="max-w-[640px]">
      <PageHeader title="My account" />
      <Card className="py-4">
        <CardContent className="flex items-center gap-3">
          <Avatar name={me.name} className="size-10 text-sm" />
          <div className="min-w-0 flex-1">
            <strong className="font-semibold">{me.name}</strong>
            <div className="text-xs text-muted-foreground">Username: {me.username}</div>
          </div>
          <Badge kind={me.role}>{me.role === "ADMIN" ? "Admin" : "Staff"}</Badge>
        </CardContent>
      </Card>
      <Card>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={submit}>
            <SectionTitle title="Change password">
              After the change, other computers where you are logged in need to log in again.
            </SectionTitle>
            <PasswordInput label="Current password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
            <PasswordInput label={`New password (at least ${MIN_PASSWORD} characters)`} value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" minLength={MIN_PASSWORD} required />
            <PasswordInput label="New password again" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
            {mismatch && <ErrorBox message="The new passwords are not the same." />}
            <ErrorBox message={action.error} />
            {done && <Notice tone="success">Password changed. Other computers where you were logged in need to log in again.</Notice>}
            <div>
              <Button type="submit" disabled={action.busy || mismatch}>
                Change password
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </Page>
  );
}
