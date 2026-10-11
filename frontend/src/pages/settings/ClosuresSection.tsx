// 假期管理（D14、D27）：诊所整天休息的日子。
// - 一键预填一年的全国 + Johor 公共假期（只加没有的日子）
// - 农历新年多休的日子、诊所自己定的休息日，要员工自己加
// - 回教节日是预估日期，导入后要核对

import { useState, type FormEvent } from "react";
import * as api from "../../api";
import { Empty, ErrorBox, Loading } from "../../components";
import { clinicToday, formatDate } from "../../format";
import { useAction, useLoad } from "../../hooks";

function AddClosureForm({ year, onAdded }: { year: number; onAdded: () => void }) {
  const [date, setDate] = useState("");
  const [reason, setReason] = useState("");
  const action = useAction();

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (await action.run(() => api.explainDuplicate(
          api.settings.addClosure({ closure_date: date, reason: reason.trim() }),
          "This date is already a closure day.",
        ))) {
      setDate("");
      setReason("");
      onAdded();
    }
  }

  return (
    <form className="card inline-form" onSubmit={submit}>
      <h3>Add a closure day</h3>
      <p className="muted small">
        For example a day the clinic decides to close. No new bookings on that day; appointments
        already there show under <em>Needs staff</em> on the Reminders page, so you can tell the patients.
      </p>
      <div className="fields">
        <label>
          Date
          <input type="date" value={date} min={`${year - 1}-01-01`} onChange={(e) => setDate(e.target.value)} required />
        </label>
        <label>
          Reason
          <input value={reason} onChange={(e) => setReason(e.target.value)} required maxLength={100} />
        </label>
      </div>
      <ErrorBox message={action.error} />
      <button type="submit" className="primary" disabled={action.busy}>Add</button>
    </form>
  );
}

export default function ClosuresSection({ canEdit }: { canEdit: boolean }) {
  const [year, setYear] = useState(() => Number(clinicToday().slice(0, 4)));
  const closures = useLoad(() => api.settings.closures(year), [year]);
  const action = useAction();
  const [imported, setImported] = useState<string | null>(null);

  async function importHolidays() {
    setImported(null);
    if (
      !window.confirm(
        `Add the public holidays the clinic closes on in ${year}? ` +
          "(New Year's Day, Chinese New Year 2 days, Hari Raya Aidilfitri 2 days, Sultan of Johor's Birthday, Labour Day, " +
          "Merdeka Day, Malaysia Day, Deepavali, Christmas Day. Replacement days are not added.) " +
          "Days already in the list are kept.",
      )
    )
      return;
    await action.run(async () => {
      const result = await api.settings.importHolidays(year);
      setImported(
        `Added ${result.added.length} day(s); ${result.already_there} were already there. ` +
          "Please check the Hari Raya dates (they are estimates) and add any other day the clinic closes.",
      );
      closures.reload();
    });
  }

  async function remove(date: string, reason: string) {
    if (window.confirm(`Delete the closure on ${formatDate(date)} (${reason})?`)) {
      if (await action.run(() => api.settings.deleteClosure(date))) closures.reload();
    }
  }

  return (
    <section>
      <div className="row-between">
        <div className="actions">
          <button type="button" onClick={() => setYear((y) => y - 1)} aria-label="Previous year">‹</button>
          <h2 className="year">{year}</h2>
          <button type="button" onClick={() => setYear((y) => y + 1)} aria-label="Next year">›</button>
        </div>
        {canEdit && (
          <button type="button" disabled={action.busy} onClick={importHolidays}>
            Import public holidays for {year}
          </button>
        )}
      </div>
      {imported && <p className="ok">{imported}</p>}
      <ErrorBox message={action.error} />
      <ErrorBox message={closures.error} onRetry={closures.reload} />
      {closures.data === undefined ? (
        closures.loading && <Loading />
      ) : closures.data.length === 0 ? (
        <Empty>No closure days in {year}. The clinic is treated as open every day.</Empty>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Reason</th>
              {canEdit && <th></th>}
            </tr>
          </thead>
          <tbody>
            {closures.data.map((c) => (
              <tr key={c.closure_date}>
                <td className="nowrap">{formatDate(c.closure_date)}</td>
                <td>{c.reason}</td>
                {canEdit && (
                  <td>
                    <button type="button" className="link" disabled={action.busy} onClick={() => remove(c.closure_date, c.reason)}>
                      Delete
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canEdit && <AddClosureForm year={year} onAdded={closures.reload} />}
    </section>
  );
}
