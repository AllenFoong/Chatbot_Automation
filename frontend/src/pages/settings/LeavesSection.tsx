// 医生请假（备用，W25）：本系统记录的请假日，那天这位医生没有空档。
// GPiS 里的 OFF DAY 记录本来就会被检查，这里是给没写进 GPiS 的请假用的。

import { useState, type FormEvent } from "react";
import * as api from "../../api";
import { Empty, ErrorBox, Loading } from "../../components";
import { clinicToday, formatDate } from "../../format";
import { useAction, useLoad } from "../../hooks";
import type { Doctor } from "../../types";

function AddLeaveForm({ doctors, onAdded }: { doctors: Doctor[]; onAdded: () => void }) {
  const [doctorId, setDoctorId] = useState("");
  const [date, setDate] = useState("");
  const [reason, setReason] = useState("");
  const action = useAction();

  async function submit(e: FormEvent) {
    e.preventDefault();
    const ok = await action.run(() =>
      api.explainDuplicate(
        api.settings.addLeave({ doctor_id: doctorId, leave_date: date, reason: reason.trim() || null }),
        "This doctor already has leave on this date.",
      ),
    );
    if (ok) {
      setDate("");
      setReason("");
      onAdded();
    }
  }

  return (
    <form className="card inline-form" onSubmit={submit}>
      <div className="card-title">
        <h3>Add doctor leave</h3>
        <p>Only for leave that is not written in GPiS as an OFF DAY.</p>
      </div>
      <div className="fields">
        <label>
          Doctor
          <select value={doctorId} onChange={(e) => setDoctorId(e.target.value)} required>
            <option value="">Choose…</option>
            {doctors.filter((d) => d.active).map((d) => (
              <option key={d.id} value={d.id}>{d.display_name}</option>
            ))}
          </select>
        </label>
        <label>
          Date
          <input type="date" value={date} min={clinicToday()} onChange={(e) => setDate(e.target.value)} required />
        </label>
        <label>
          Reason (optional)
          <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={100} />
        </label>
      </div>
      <ErrorBox message={action.error} />
      <button type="submit" className="primary" disabled={action.busy}>Add leave</button>
    </form>
  );
}

export default function LeavesSection({ canEdit }: { canEdit: boolean }) {
  const leaves = useLoad(() => api.settings.leaves(), []);
  const doctors = useLoad(() => api.settings.doctors(), []);
  const action = useAction();
  const names = new Map((doctors.data ?? []).map((d) => [d.id, d.display_name]));

  async function remove(doctorId: string, date: string) {
    if (window.confirm(`Delete the leave of ${names.get(doctorId) ?? doctorId} on ${formatDate(date)}?`)) {
      if (await action.run(() => api.settings.deleteLeave(doctorId, date))) leaves.reload();
    }
  }

  return (
    <section>
      <p className="muted section-intro">
        Leave from today onwards. A doctor on leave has no free slots that day. "OFF DAY" records in GPiS are
        also respected, so this list is only for leave that is not in GPiS.
      </p>
      <ErrorBox message={action.error} />
      <ErrorBox message={leaves.error ?? doctors.error} onRetry={leaves.reload} />
      {leaves.data === undefined ? (
        leaves.loading && <Loading />
      ) : leaves.data.length === 0 ? (
        <Empty>No upcoming doctor leave.</Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Doctor</th>
                <th>Reason</th>
                {canEdit && <th aria-label="Actions"></th>}
              </tr>
            </thead>
            <tbody>
              {leaves.data.map((l) => (
                <tr key={`${l.doctor_id}-${l.leave_date}`}>
                  <td className="nowrap">{formatDate(l.leave_date)}</td>
                  <td>{names.get(l.doctor_id) ?? l.doctor_id}</td>
                  <td>{l.reason}</td>
                  {canEdit && (
                    <td className="cell-actions">
                      <button type="button" className="small danger-text" disabled={action.busy} onClick={() => remove(l.doctor_id, l.leave_date)}>
                        Delete
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {canEdit && doctors.data && <AddLeaveForm doctors={doctors.data} onAdded={leaves.reload} />}
    </section>
  );
}
