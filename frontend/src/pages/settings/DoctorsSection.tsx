// 医生和每星期的排班。离职的医生改成 inactive，不删除（旧的预约请求还会用到）。
// 排班的时间只能选 30 分钟的格（数据库也会检查）。

import { useEffect, useState, type FormEvent } from "react";
import * as api from "../../api";
import { Badge, Empty, ErrorBox, Loading } from "../../components";
import { HALF_HOURS, formatTime, weekdayName } from "../../format";
import { useAction, useLoad } from "../../hooks";
import { scheduleProblems } from "../../schedule";
import type { Doctor, ScheduleDay } from "../../types";

function TimeSelect({
  label,
  value,
  onChange,
  disabled,
  optional,
}: {
  label: string;
  value: string | null;
  onChange: (value: string | null) => void;
  disabled: boolean;
  optional?: boolean;
}) {
  return (
    <select
      aria-label={label}
      value={value ? formatTime(value) : ""}
      onChange={(e) => onChange(e.target.value || null)}
      disabled={disabled}
    >
      <option value="">{optional ? "None" : "—"}</option>
      {HALF_HOURS.map((t) => (
        <option key={t} value={t}>
          {t}
        </option>
      ))}
    </select>
  );
}

function ScheduleEditor({ doctor, canEdit }: { doctor: Doctor; canEdit: boolean }) {
  const schedule = useLoad(() => api.settings.schedule(doctor.id), [doctor.id]);
  const [days, setDays] = useState<ScheduleDay[]>([]);
  const [saved, setSaved] = useState(false);
  const action = useAction();

  useEffect(() => {
    if (schedule.data) setDays(schedule.data);
  }, [schedule.data]);

  function update(weekday: number, change: Partial<ScheduleDay>) {
    setSaved(false);
    setDays((ds) => ds.map((d) => (d.weekday === weekday ? { ...d, ...change } : d)));
  }

  const problems = scheduleProblems(days);

  async function save() {
    setSaved(false);
    if (problems.length > 0) return;
    if (await action.run(async () => setDays(await api.settings.setSchedule(doctor.id, days)))) setSaved(true);
  }

  if (schedule.data === undefined) {
    return (
      <>
        <ErrorBox message={schedule.error} onRetry={schedule.reload} />
        {schedule.loading && <Loading />}
      </>
    );
  }

  return (
    <div className="card">
      <h3>Weekly schedule – {doctor.display_name}</h3>
      <p className="muted small">
        "Last slot" is the last time a 30-minute appointment can start. Slots from "break start" up to (not
        including) "break end" cannot be booked.
      </p>
      <table>
        <thead>
          <tr>
            <th>Day</th>
            <th>Working</th>
            <th>Start</th>
            <th>Last slot</th>
            <th>Break start</th>
            <th>Break end</th>
          </tr>
        </thead>
        <tbody>
          {days.map((d) => {
            const name = weekdayName(d.weekday);
            const off = !d.is_working;
            return (
              <tr key={d.weekday} className={off ? "off" : undefined}>
                <td>{name}</td>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`${name} working`}
                    checked={d.is_working}
                    disabled={!canEdit}
                    onChange={(e) => update(d.weekday, { is_working: e.target.checked })}
                  />
                </td>
                <td>
                  <TimeSelect label={`${name} start`} value={d.start_time} disabled={!canEdit || off}
                    onChange={(v) => update(d.weekday, { start_time: v })} />
                </td>
                <td>
                  <TimeSelect label={`${name} last slot`} value={d.last_slot} disabled={!canEdit || off}
                    onChange={(v) => update(d.weekday, { last_slot: v })} />
                </td>
                <td>
                  <TimeSelect label={`${name} break start`} value={d.break_start} disabled={!canEdit || off} optional
                    onChange={(v) => update(d.weekday, { break_start: v })} />
                </td>
                <td>
                  <TimeSelect label={`${name} break end`} value={d.break_end} disabled={!canEdit || off} optional
                    onChange={(v) => update(d.weekday, { break_end: v })} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {canEdit && problems.length > 0 && (
        <ul className="error" role="alert">
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
      <ErrorBox message={action.error} />
      {canEdit && (
        <div className="actions">
          <button type="button" className="primary" disabled={action.busy || problems.length > 0} onClick={save}>
            Save schedule
          </button>
          {saved && <span className="ok">Saved.</span>}
        </div>
      )}
    </div>
  );
}

function DoctorRow({ doctor, canEdit, selected, onSelect, onChanged }: {
  doctor: Doctor;
  canEdit: boolean;
  selected: boolean;
  onSelect: () => void;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(doctor.display_name);
  const [tag, setTag] = useState(doctor.remark_tag ?? "");
  const action = useAction();

  async function save(e: FormEvent) {
    e.preventDefault();
    const ok = await action.run(() =>
      api.settings.updateDoctor(doctor.id, { display_name: name.trim(), remark_tag: tag.trim() || null }),
    );
    if (ok) {
      setEditing(false);
      onChanged();
    }
  }

  async function toggleActive() {
    const question = doctor.active
      ? `Mark ${doctor.display_name} as inactive (left the clinic)?`
      : `Mark ${doctor.display_name} as active again?`;
    if (window.confirm(question) && (await action.run(() => api.settings.updateDoctor(doctor.id, { active: !doctor.active })))) {
      onChanged();
    }
  }

  return (
    <tr className={selected ? "selected" : undefined}>
      <td>{doctor.id}</td>
      {editing ? (
        <td colSpan={2}>
          <form className="inline" onSubmit={save}>
            <input aria-label="Display name" value={name} onChange={(e) => setName(e.target.value)} required />
            <input aria-label="Remark tag" value={tag} onChange={(e) => setTag(e.target.value)} size={4} maxLength={5} />
            <button type="submit" className="primary" disabled={action.busy}>Save</button>
            <button type="button" onClick={() => setEditing(false)}>Cancel</button>
          </form>
          <ErrorBox message={action.error} />
        </td>
      ) : (
        <>
          <td>{doctor.display_name}</td>
          <td>{doctor.remark_tag}</td>
        </>
      )}
      <td>{doctor.active ? <Badge kind="ok">Active</Badge> : <Badge kind="closed">Inactive</Badge>}</td>
      <td className="actions">
        <button type="button" onClick={onSelect} disabled={selected}>Schedule</button>
        {canEdit && !editing && (
          <>
            <button type="button" onClick={() => setEditing(true)}>Edit</button>
            <button type="button" onClick={toggleActive} disabled={action.busy}>
              {doctor.active ? "Deactivate" : "Activate"}
            </button>
          </>
        )}
        {!editing && <ErrorBox message={action.error} />}
      </td>
    </tr>
  );
}

function AddDoctorForm({ onAdded }: { onAdded: (id: string) => void }) {
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [tag, setTag] = useState("");
  const action = useAction();

  async function submit(e: FormEvent) {
    e.preventDefault();
    const ok = await action.run(async () => {
      const d = await api.explainDuplicate(
        api.settings.addDoctor({ id: id.trim(), display_name: name.trim(), remark_tag: tag.trim() || null }),
        "A doctor with this ID already exists.",
      );
      onAdded(d.id);
    });
    if (ok) {
      setId("");
      setName("");
      setTag("");
    }
  }

  return (
    <form className="card inline-form" onSubmit={submit}>
      <h3>Add a doctor</h3>
      <p className="muted small">The new doctor starts with every day off. Set the working days in the schedule.</p>
      <div className="fields">
        <label>
          GPiS DoctorID
          <input value={id} onChange={(e) => setId(e.target.value.toUpperCase())} required maxLength={20} />
        </label>
        <label>
          Display name
          <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} />
        </label>
        <label>
          Remark tag (e.g. P)
          <input value={tag} onChange={(e) => setTag(e.target.value)} maxLength={5} size={4} />
        </label>
      </div>
      <ErrorBox message={action.error} />
      <button type="submit" className="primary" disabled={action.busy}>Add doctor</button>
    </form>
  );
}

export default function DoctorsSection({ canEdit }: { canEdit: boolean }) {
  const doctors = useLoad(() => api.settings.doctors(), []);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const list = doctors.data ?? [];
  const selected = list.find((d) => d.id === selectedId) ?? list.find((d) => d.active) ?? null;

  return (
    <section>
      <ErrorBox message={doctors.error} onRetry={doctors.reload} />
      {doctors.data === undefined ? (
        doctors.loading && <Loading />
      ) : list.length === 0 ? (
        <Empty>No doctors yet.</Empty>
      ) : (
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Remark tag</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {list.map((d) => (
              <DoctorRow key={`${d.id}-${d.display_name}-${d.remark_tag}-${d.active}`} doctor={d} canEdit={canEdit}
                selected={d.id === selected?.id} onSelect={() => setSelectedId(d.id)} onChanged={doctors.reload} />
            ))}
          </tbody>
        </table>
      )}
      {selected && <ScheduleEditor key={selected.id} doctor={selected} canEdit={canEdit} />}
      {canEdit && (
        <AddDoctorForm
          onAdded={(id) => {
            setSelectedId(id);
            doctors.reload();
          }}
        />
      )}
    </section>
  );
}
