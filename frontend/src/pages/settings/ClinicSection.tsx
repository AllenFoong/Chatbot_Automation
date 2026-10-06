// 每格上限（W22、D15）和 GPiS 里诊所自己的 ContactID（统计 B6）。
// 数据库只接受 1–3（D19），画面也只给 1–3 选。

import { useEffect, useState, type FormEvent } from "react";
import * as api from "../../api";
import { ErrorBox, Loading } from "../../components";
import { useAction, useLoad } from "../../hooks";
import type { ClinicSettings } from "../../types";

export default function ClinicSection({ canEdit }: { canEdit: boolean }) {
  const settings = useLoad(() => api.settings.clinic(), []);
  const [form, setForm] = useState<ClinicSettings | null>(null);
  const [saved, setSaved] = useState(false);
  const action = useAction();

  useEffect(() => {
    if (settings.data) setForm(settings.data);
  }, [settings.data]);

  function change(patch: Partial<ClinicSettings>) {
    setSaved(false);
    setForm((f) => (f ? { ...f, ...patch } : f));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form) return;
    if (await action.run(async () => setForm(await api.settings.updateClinic(form)))) setSaved(true);
  }

  if (!form) {
    return (
      <>
        <ErrorBox message={settings.error} onRetry={settings.reload} />
        {settings.loading && <Loading />}
      </>
    );
  }

  const choices = [1, 2, 3];
  return (
    <form className="card inline-form" onSubmit={submit}>
      <label>
        Patients per slot (at most)
        <select value={form.max_per_slot} disabled={!canEdit} onChange={(e) => change({ max_per_slot: Number(e.target.value) })}>
          {choices.map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </label>
      <p className="muted small">The 3rd place is only for short treatments ("Can be 3rd") and only when the slots next to it are not full.</p>

      <label>
        Patients per slot the AI may book (at most)
        <select value={form.max_per_slot_for_ai} disabled={!canEdit} onChange={(e) => change({ max_per_slot_for_ai: Number(e.target.value) })}>
          {choices.map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </label>
      <p className="muted small">Set to 2 to keep the 3rd place for staff only.</p>

      <label>
        Clinic's own ContactID in GPiS
        <input type="number" min={1} value={form.clinic_contact_id} disabled={!canEdit}
          onChange={(e) => change({ clinic_contact_id: Number(e.target.value) })} required />
      </label>
      <p className="muted small">Appointments under this contact (other than OFF DAY) mark the day for staff review.</p>

      <ErrorBox message={action.error} />
      {canEdit && (
        <div className="actions">
          <button type="submit" className="primary" disabled={action.busy}>Save</button>
          {saved && <span className="ok">Saved.</span>}
        </div>
      )}
    </form>
  );
}
