// 员工账号（只有 ADMIN，D25）。离职的员工停用（旧的记录还会指向他）。
// 后端保证至少留一个 active 的 ADMIN；停用、重设密码后，那个人已经登录的也马上失效（D26）。
// Delete（D75）：只有没在系统里做过事的账号（建错、重复的）删得掉；做过事的，后端说明原因、请改用停用。

import { useState, type FormEvent } from "react";
import * as api from "../api";
import { useUser } from "../auth";
import { Badge, ErrorBox, Field, Loading, Page, PageHeader, PasswordInput, SectionTitle } from "../components";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { NativeSelect } from "../components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { cn } from "../lib/utils";
import { useAction, useLoad } from "../hooks";
import type { Role, StaffMember } from "../types";

const MIN_PASSWORD = 8; // = backend/app/auth.py MIN_PASSWORD_LENGTH

function ResetPasswordForm({ member, onDone }: { member: StaffMember; onDone: () => void }) {
  const [password, setPassword] = useState("");
  const action = useAction();

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (await action.run(() => api.staff.update(member.id, { password }))) onDone();
  }

  return (
    <form className="flex flex-wrap items-center justify-end gap-2" onSubmit={submit}>
      <PasswordInput aria-label={`New password for ${member.username}`} placeholder="New password" className="w-48"
        autoComplete="new-password" minLength={MIN_PASSWORD} value={password} onChange={(e) => setPassword(e.target.value)} required />
      <Button type="submit" size="sm" disabled={action.busy}>Set password</Button>
      <Button type="button" size="sm" variant="outline" onClick={onDone}>Cancel</Button>
      <ErrorBox message={action.error} />
    </form>
  );
}

function StaffRow({ member, isMe, onChanged }: { member: StaffMember; isMe: boolean; onChanged: () => void }) {
  const [resetting, setResetting] = useState(false);
  const action = useAction();

  async function update(question: string, patch: Parameters<typeof api.staff.update>[1]) {
    if (window.confirm(question) && (await action.run(() => api.staff.update(member.id, patch)))) onChanged();
  }

  return (
    <>
    <TableRow className={cn(!member.active && "text-muted-foreground")}>
      <TableCell><strong className="font-semibold">{member.username}</strong>{isMe && <span className="text-muted-foreground"> (you)</span>}</TableCell>
      <TableCell>{member.name}</TableCell>
      <TableCell><Badge kind={member.role}>{member.role}</Badge></TableCell>
      <TableCell>{member.active ? <Badge kind="ok">Active</Badge> : <Badge kind="closed">Inactive</Badge>}</TableCell>
      <TableCell className="text-right">
        {resetting ? (
          <ResetPasswordForm member={member} onDone={() => setResetting(false)} />
        ) : (
          <div className="flex justify-end gap-1.5 whitespace-nowrap">
            <Button type="button" size="sm" variant="outline" disabled={action.busy}
              onClick={() => {
                const role: Role = member.role === "ADMIN" ? "STAFF" : "ADMIN";
                void update(`Change ${member.username} to ${role}?`, { role });
              }}>
              Make {member.role === "ADMIN" ? "staff" : "admin"}
            </Button>
            <Button type="button" size="sm" variant={member.active ? "ghost-destructive" : "outline"} disabled={action.busy}
              onClick={() =>
                update(
                  member.active
                    ? `Deactivate ${member.username}? They are logged out at once and cannot log in.${isMe ? " This is your own account." : ""}`
                    : `Activate ${member.username} again?`,
                  { active: !member.active },
                )
              }>
              {member.active ? "Deactivate" : "Activate"}
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => setResetting(true)}>Reset password</Button>
            {!isMe && (
              <Button type="button" size="sm" variant="ghost-destructive" disabled={action.busy}
                onClick={async () => {
                  if (window.confirm(`Delete ${member.username} permanently? Only accounts that were never used can be deleted; for a leaver, use Deactivate.`)
                    && (await action.run(() => api.staff.remove(member.id)))) onChanged();
                }}>
                Delete
              </Button>
            )}
          </div>
        )}
      </TableCell>
    </TableRow>
    {action.error && (
      // 错误另起一整行（例：删不掉的原因很长），不要挤在按钮那一格
      <TableRow className="hover:bg-transparent">
        <TableCell colSpan={5}>
          <ErrorBox message={action.error} />
        </TableCell>
      </TableRow>
    )}
    </>
  );
}

function AddStaffForm({ onAdded }: { onAdded: () => void }) {
  const [username, setUsername] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("STAFF");
  const [password, setPassword] = useState("");
  const [added, setAdded] = useState(0); // 加好一个账号：密码栏换新的（回到隐藏）
  const action = useAction();

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (await action.run(() => api.explainDuplicate(
          api.staff.add({ username: username.trim(), name: name.trim(), role, password }),
          "This username is already taken.",
        ))) {
      setUsername("");
      setName("");
      setRole("STAFF");
      setPassword("");
      setAdded((n) => n + 1);
      onAdded();
    }
  }

  return (
    <Card>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <SectionTitle title="Add a staff account">
            Give the first password to the person directly (not by WhatsApp group). They can change it under their
            name at the bottom left.
          </SectionTitle>
          <div className="grid items-end gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Username">
              <Input value={username} onChange={(e) => setUsername(e.target.value.toLowerCase())} autoComplete="off" required />
            </Field>
            <Field label="Name">
              <Input value={name} onChange={(e) => setName(e.target.value)} required />
            </Field>
            <Field label="Role">
              <NativeSelect value={role} onChange={(e) => setRole(e.target.value as Role)}>
                <option value="STAFF">Staff</option>
                <option value="ADMIN">Admin (settings, accounts)</option>
              </NativeSelect>
            </Field>
            <PasswordInput key={added} label={`Password (at least ${MIN_PASSWORD} characters)`} value={password}
              onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" minLength={MIN_PASSWORD} required />
          </div>
          <ErrorBox message={action.error} />
          <div>
            <Button type="submit" disabled={action.busy}>Add account</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export default function StaffPage() {
  const me = useUser();
  const list = useLoad(() => api.staff.list(), []);

  return (
    <Page>
      <PageHeader
        title="Staff accounts"
        description="Who can log in. Deactivate leavers (their history stays); delete only accounts made by mistake. Admins can also change settings and accounts."
      />
      <ErrorBox message={list.error} onRetry={list.reload} />
      {list.data === undefined ? (
        list.loading && <Loading />
      ) : (
        <Card className="gap-0 overflow-hidden py-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Username</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead aria-label="Actions"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.data.map((m) => (
                <StaffRow key={`${m.id}-${m.role}-${m.active}`} member={m} isMe={m.id === me.id} onChanged={list.reload} />
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
      <AddStaffForm onAdded={list.reload} />
    </Page>
  );
}
