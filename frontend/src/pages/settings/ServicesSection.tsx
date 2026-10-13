// 疗程代码（和 GPiS Remarks 同一套）。这些设定决定 AI 能不能自己约、能不能当一格的第 3 人（D15、D16）。
// 不再提供的疗程改成 inactive，不删除（旧的预约请求还会用到）。

import { useState, type FormEvent } from "react";
import * as api from "../../api";
import { Badge, ErrorBox, Loading } from "../../components";
import { CheckIcon } from "../../icons";
import { useAction, useLoad } from "../../hooks";
import type { Service, ServiceIn } from "../../types";

// 多步骤疗程：后续预约要同一位医生（W9、D21、D33）。和 backend/app/db/seed.py 用的类别一样
const TREATMENT_GROUPS = ["IMPLANT", "DENTURE", "ORTHO", "RCT", "CROWN", "BRIDGE"];

const FLAGS = [
  { key: "ai_can_book", label: "AI can book", help: "The AI may suggest a time by itself. If not, the AI collects the request and passes it to staff." },
  { key: "can_be_third", label: "Can be 3rd", help: "May use the 3rd place in a slot (short treatments)." },
  { key: "may_need_1h", label: "May need 1 h", help: "Staff decide if it needs 1 hour, so the AI passes it to staff." },
] as const;

type Draft = ServiceIn & { active: boolean };

function GroupSelect({ value, onChange }: { value: string | null; onChange: (v: string | null) => void }) {
  // 数据库里有这里不认识的类别时也要显示出来，不能看起来像 "single visit"
  const groups = value && !TREATMENT_GROUPS.includes(value) ? [...TREATMENT_GROUPS, value] : TREATMENT_GROUPS;
  return (
    <select aria-label="Treatment group" value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">— (single visit)</option>
      {groups.map((g) => (
        <option key={g} value={g}>{g}</option>
      ))}
    </select>
  );
}

function ServiceRow({ service, canEdit, onChanged }: { service: Service; canEdit: boolean; onChanged: () => void }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const action = useAction();

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!draft) return;
    const { code: _code, ...changes } = draft;
    if (await action.run(() => api.settings.updateService(service.code, { ...changes, name: changes.name.trim() }))) {
      setDraft(null);
      onChanged();
    }
  }

  if (draft) {
    return (
      <tr className="editing">
        <td><strong>{service.code}</strong></td>
        <td colSpan={7}>
          <form className="inline" onSubmit={save}>
            <input aria-label="Name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} required maxLength={100} />
            {FLAGS.map((f) => (
              <label key={f.key} className="check" title={f.help}>
                <input type="checkbox" checked={draft[f.key]} onChange={(e) => setDraft({ ...draft, [f.key]: e.target.checked })} />
                {f.label}
              </label>
            ))}
            <GroupSelect value={draft.treatment_group} onChange={(v) => setDraft({ ...draft, treatment_group: v })} />
            <label className="check">
              <input type="checkbox" checked={draft.active} onChange={(e) => setDraft({ ...draft, active: e.target.checked })} />
              Active
            </label>
            <button type="submit" className="primary small" disabled={action.busy}>Save</button>
            <button type="button" className="small" onClick={() => setDraft(null)}>Cancel</button>
          </form>
          <ErrorBox message={action.error} />
        </td>
      </tr>
    );
  }

  return (
    <tr className={service.active ? undefined : "off"}>
      <td><strong>{service.code}</strong></td>
      <td>{service.name}</td>
      {FLAGS.map((f) => (
        <td key={f.key} className="center-cell">
          {service[f.key] && (
            <span className="yes" title="Yes">
              <CheckIcon size={16} />
            </span>
          )}
        </td>
      ))}
      <td>{service.treatment_group && <span className="tag">{service.treatment_group}</span>}</td>
      <td>{service.active ? <Badge kind="ok">Active</Badge> : <Badge kind="closed">Inactive</Badge>}</td>
      <td className="cell-actions">
        {canEdit && (
          <button type="button" className="small" onClick={() => setDraft({ ...service })}>Edit</button>
        )}
      </td>
    </tr>
  );
}

const EMPTY: ServiceIn = { code: "", name: "", can_be_third: false, may_need_1h: false, ai_can_book: false, treatment_group: null };

function AddServiceForm({ onAdded }: { onAdded: () => void }) {
  const [form, setForm] = useState<ServiceIn>(EMPTY);
  const action = useAction();

  async function submit(e: FormEvent) {
    e.preventDefault();
    const ok = await action.run(() => api.explainDuplicate(
        api.settings.addService({ ...form, code: form.code.trim(), name: form.name.trim() }),
        "This treatment code already exists.",
      ));
    if (ok) {
      setForm(EMPTY);
      onAdded();
    }
  }

  return (
    <form className="card inline-form" onSubmit={submit}>
      <div className="card-title">
        <h3>Add a treatment</h3>
        <p>Use the same code staff write in GPiS Remarks.</p>
      </div>
      <div className="fields">
        <label>
          Code
          <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} required maxLength={20} size={8} />
        </label>
        <label>
          Name
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required maxLength={100} />
        </label>
        <label>
          Group
          <GroupSelect value={form.treatment_group} onChange={(v) => setForm({ ...form, treatment_group: v })} />
        </label>
      </div>
      <div className="checks">
        {FLAGS.map((f) => (
          <label key={f.key} className="check" title={f.help}>
            <input type="checkbox" checked={form[f.key]} onChange={(e) => setForm({ ...form, [f.key]: e.target.checked })} />
            {f.label}
          </label>
        ))}
      </div>
      <ErrorBox message={action.error} />
      <button type="submit" className="primary" disabled={action.busy}>Add treatment</button>
    </form>
  );
}

export default function ServicesSection({ canEdit }: { canEdit: boolean }) {
  const services = useLoad(() => api.settings.services(), []);

  return (
    <section>
      <ul className="legend">
        {FLAGS.map((f) => (
          <li key={f.key}><strong>{f.label}</strong>: {f.help}</li>
        ))}
        <li><strong>Group</strong>: multi-step treatment; follow-up visits must be with the same doctor.</li>
      </ul>
      <ErrorBox message={services.error} onRetry={services.reload} />
      {services.data === undefined ? (
        services.loading && <Loading />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Code</th>
                <th>Name</th>
                {FLAGS.map((f) => (
                  <th key={f.key}>{f.label}</th>
                ))}
                <th>Group</th>
                <th>Status</th>
                <th aria-label="Actions"></th>
              </tr>
            </thead>
            <tbody>
              {services.data.map((s) => (
                <ServiceRow key={`${JSON.stringify(s)}`} service={s} canEdit={canEdit} onChanged={services.reload} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {canEdit && <AddServiceForm onAdded={services.reload} />}
    </section>
  );
}
