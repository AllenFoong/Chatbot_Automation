// 预约请求（D6）：AI 或员工建的请求，员工在 GPiS 录入后按 Confirm；或者 Reject、Cancel。
// - PENDING 先来的排前面（先处理）；其他状态最近的排前面（后端决定）。
// - 一起来的几位病人（group_id 一样，= Remarks 的 WITH）标出"Together with …"。
// - 这里只改本系统的状态，不会写入 GPiS（D5）：确认前员工要自己在 GPiS 录入。

import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import * as api from "../api";
import { Badge, Empty, ErrorBox, Loading, PageHeader, Tabs } from "../components";
import { formatDate, formatDateTime, formatPhone, formatTime } from "../format";
import { useAction, useLoad } from "../hooks";
import { RefreshIcon } from "../icons";
import type { AppointmentRequest, RequestStatus } from "../types";

const STATUSES: { value: RequestStatus; label: string }[] = [
  { value: "PENDING", label: "Pending" },
  { value: "CONFIRMED", label: "Confirmed" },
  { value: "REJECTED", label: "Rejected" },
  { value: "CANCELLED", label: "Cancelled" },
];

const STATUS_LABEL: Record<RequestStatus, string> = {
  PENDING: "Pending",
  CONFIRMED: "Confirmed",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
};

/** 同一组（一起来）的其他病人名字 */
function groupMates(r: AppointmentRequest, all: AppointmentRequest[]): string[] {
  if (!r.group_id) return [];
  return all.filter((o) => o.group_id === r.group_id && o.id !== r.id).map((o) => o.customer_name);
}

function ConfirmForm({ request, onDone, onCancel }: { request: AppointmentRequest; onDone: () => void; onCancel: () => void }) {
  const [gpisId, setGpisId] = useState("");
  const action = useAction();

  async function submit(e: FormEvent) {
    e.preventDefault();
    const id = gpisId.trim() === "" ? null : Number(gpisId);
    if (await action.run(() => api.requests.confirm(request.id, id))) onDone();
  }

  return (
    <form className="inline-form confirm-form" onSubmit={submit}>
      <p className="small">Only confirm after you have entered this appointment in GPiS.</p>
      <label>
        GPiS AppointmentID (optional)
        <input
          inputMode="numeric"
          pattern="[0-9]*"
          value={gpisId}
          onChange={(e) => setGpisId(e.target.value)}
          placeholder="Leave empty if unknown"
        />
      </label>
      <ErrorBox message={action.error} />
      <div className="actions">
        <button type="submit" className="primary" disabled={action.busy}>
          Entered in GPiS – confirm
        </button>
        <button type="button" onClick={onCancel} disabled={action.busy}>
          Back
        </button>
      </div>
    </form>
  );
}

function RequestCard({ request: r, all, onChanged }: { request: AppointmentRequest; all: AppointmentRequest[]; onChanged: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const action = useAction();
  const mates = groupMates(r, all);

  async function change(question: string, fn: (id: number) => Promise<AppointmentRequest>) {
    if (window.confirm(question) && (await action.run(() => fn(r.id)))) onChanged();
  }

  return (
    <li className="card request">
      <div className="card-head">
        <div>
          <strong>{r.customer_name}</strong>
          {r.customer_phone && <div className="phone muted">{formatPhone(r.customer_phone)}</div>}
          <div className="muted small">
            {r.gpis_contact_id ? `GPiS ContactID ${r.gpis_contact_id}` : "Not linked to a GPiS contact"}
          </div>
        </div>
        <Badge kind={r.status}>{STATUS_LABEL[r.status]}</Badge>
      </div>

      <dl className="facts">
        <dt>Treatment</dt>
        <dd>
          <strong>{r.service_code}</strong> {r.service_name}
        </dd>
        <dt>Doctor</dt>
        <dd>{r.doctor_id ?? "Any"}</dd>
        <dt>Preferred</dt>
        <dd>
          {r.preferred_date ? formatDate(r.preferred_date) : "No date yet"}
          {r.preferred_slot && ` ${formatTime(r.preferred_slot)}`}
        </dd>
        <dt>Duration</dt>
        <dd>{r.duration_minutes === 60 ? "1 hour" : `${r.duration_minutes} min`}</dd>
        {mates.length > 0 && (
          <>
            <dt>Together with</dt>
            <dd>{mates.join(", ")}</dd>
          </>
        )}
        {r.notes && (
          <>
            <dt>Notes</dt>
            <dd>{r.notes}</dd>
          </>
        )}
        {r.gpis_appointment_id !== null && (
          <>
            <dt>GPiS AppointmentID</dt>
            <dd>{r.gpis_appointment_id}</dd>
          </>
        )}
      </dl>

      <div className="card-meta muted small">
        Requested {formatDateTime(r.created_at)}
        {r.handled_at && ` · updated ${formatDateTime(r.handled_at)}`}
        {r.conversation_id !== null && (
          <>
            {" · "}
            <Link to={`/conversations/${r.conversation_id}`}>Open conversation</Link>
          </>
        )}
      </div>

      <ErrorBox message={action.error} />

      {confirming ? (
        <ConfirmForm
          request={r}
          onDone={() => {
            setConfirming(false);
            onChanged();
          }}
          onCancel={() => setConfirming(false)}
        />
      ) : (
        (r.status === "PENDING" || r.status === "CONFIRMED") && (
          <div className="card-actions actions">
            {r.status === "PENDING" && (
              <>
                <button type="button" className="primary" disabled={action.busy} onClick={() => setConfirming(true)}>
                  Confirm
                </button>
                <button
                  type="button"
                  disabled={action.busy}
                  onClick={() => change(`Reject the request for ${r.customer_name}?`, api.requests.reject)}
                >
                  Reject
                </button>
              </>
            )}
            <button
              type="button"
              className="ghost"
              disabled={action.busy}
              onClick={() =>
                change(
                  r.status === "CONFIRMED"
                    ? `Cancel the confirmed appointment for ${r.customer_name}? Remember to also mark it Canceled in GPiS.`
                    : `The patient cancelled: cancel the request for ${r.customer_name}?`,
                  api.requests.cancel,
                )
              }
            >
              Patient cancelled
            </button>
          </div>
        )
      )}
    </li>
  );
}

export default function RequestsPage() {
  const [status, setStatus] = useState<RequestStatus>("PENDING");
  const list = useLoad(() => api.requests.list(status), [status], 30_000);

  return (
    <div className="page">
      <PageHeader
        title="Appointment requests"
        description="Booking requests waiting for GPiS. Enter each one in GPiS first, then confirm it here."
        actions={
          <button type="button" onClick={list.reload}>
            <RefreshIcon />
            Refresh
          </button>
        }
      />
      <Tabs label="Request status" value={status} options={STATUSES} onChange={setStatus} />
      <ErrorBox message={list.error} onRetry={list.reload} />
      {list.data === undefined ? (
        list.loading && <Loading />
      ) : list.data.length === 0 ? (
        <Empty>No {status.toLowerCase()} requests.</Empty>
      ) : (
        <ul className="cards">
          {list.data.map((r) => (
            <RequestCard key={r.id} request={r} all={list.data ?? []} onChanged={list.reload} />
          ))}
        </ul>
      )}
    </div>
  );
}
