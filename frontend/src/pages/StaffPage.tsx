// 员工账号（只有 ADMIN，D25）。离职的员工停用，不删除（旧的记录还会指向他）。
// 后端保证至少留一个 active 的 ADMIN；停用、重设密码后，那个人已经登录的也马上失效（D26）。

import { useState, type FormEvent } from "react";
import * as api from "../api";
import { useUser } from "../auth";
import { Badge, ErrorBox, Loading, PageHeader } from "../components";
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
    <form className="inline" onSubmit={submit}>
      <input type="password" aria-label={`New password for ${member.username}`} placeholder="New password"
        autoComplete="new-password" minLength={MIN_PASSWORD} value={password} onChange={(e) => setPassword(e.target.value)} required />
      <button type="submit" className="primary small" disabled={action.busy}>Set password</button>
      <button type="button" className="small" onClick={onDone}>Cancel</button>
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
    <tr className={member.active ? undefined : "off"}>
      <td><strong>{member.username}</strong>{isMe && <span className="muted"> (you)</span>}</td>
      <td>{member.name}</td>
      <td><Badge kind={member.role}>{member.role}</Badge></td>
      <td>{member.active ? <Badge kind="ok">Active</Badge> : <Badge kind="closed">Inactive</Badge>}</td>
      <td className="cell-actions">
        {resetting ? (
          <ResetPasswordForm member={member} onDone={() => setResetting(false)} />
        ) : (
          <div className="row-actions">
            <button type="button" className="small" disabled={action.busy}
              onClick={() => {
                const role: Role = member.role === "ADMIN" ? "STAFF" : "ADMIN";
                void update(`Change ${member.username} to ${role}?`, { role });
              }}>
              Make {member.role === "ADMIN" ? "staff" : "admin"}
            </button>
            <button type="button" className={member.active ? "small danger-text" : "small"} disabled={action.busy}
              onClick={() =>
                update(
                  member.active
                    ? `Deactivate ${member.username}? They are logged out at once and cannot log in.${isMe ? " This is your own account." : ""}`
                    : `Activate ${member.username} again?`,
                  { active: !member.active },
                )
              }>
              {member.active ? "Deactivate" : "Activate"}
            </button>
            <button type="button" className="small" onClick={() => setResetting(true)}>Reset password</button>
          </div>
        )}
        <ErrorBox message={action.error} />
      </td>
    </tr>
  );
}

function AddStaffForm({ onAdded }: { onAdded: () => void }) {
  const [username, setUsername] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("STAFF");
  const [password, setPassword] = useState("");
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
      onAdded();
    }
  }

  return (
    <form className="card inline-form" onSubmit={submit}>
      <div className="card-title">
        <h3>Add a staff account</h3>
        <p>
          Give the first password to the person directly (not by WhatsApp group). They can change it under their name
          at the bottom left.
        </p>
      </div>
      <div className="fields">
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value.toLowerCase())} autoComplete="off" required />
        </label>
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Role
          <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            <option value="STAFF">Staff</option>
            <option value="ADMIN">Admin (settings, accounts)</option>
          </select>
        </label>
        <label>
          Password (at least {MIN_PASSWORD} characters)
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password" minLength={MIN_PASSWORD} required />
        </label>
      </div>
      <ErrorBox message={action.error} />
      <button type="submit" className="primary" disabled={action.busy}>Add account</button>
    </form>
  );
}

export default function StaffPage() {
  const me = useUser();
  const list = useLoad(() => api.staff.list(), []);

  return (
    <div className="page">
      <PageHeader
        title="Staff accounts"
        description="Who can log in. Leavers are deactivated, not deleted. Admins can also change settings and accounts."
      />
      <ErrorBox message={list.error} onRetry={list.reload} />
      {list.data === undefined ? (
        list.loading && <Loading />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Username</th>
                <th>Name</th>
                <th>Role</th>
                <th>Status</th>
                <th aria-label="Actions"></th>
              </tr>
            </thead>
            <tbody>
              {list.data.map((m) => (
                <StaffRow key={`${m.id}-${m.role}-${m.active}`} member={m} isMe={m.id === me.id} onChanged={list.reload} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      <AddStaffForm onAdded={list.reload} />
    </div>
  );
}
