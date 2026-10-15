// 预约请求（D6、D71）：AI 或员工建的请求，员工在 GPiS 录入后确认；或者 Reject、Cancel。
// - PENDING 先来的排前面（先处理）；其他状态最近的排前面（后端决定）。
// - 一起来的几位病人（group_id 一样，= Remarks 的 WITH）标出"Together with …"。
// - 这里只改本系统的状态，不会写入 GPiS（D5）：确认前员工要自己在 GPiS 录入。
// - Entered in GPiS ✓（D71 ①）：当场查 GPiS 那一天的预约，员工点选是哪一个；GPiS 里没有就不能确认。
//   和请求一样的排在最上面（同一位病人、同医生、同时段），但还是要员工自己选。
// - 确认后系统马上经 WhatsApp 通知病人；发不了的（超过 24 小时、读 GPiS_Dev …）放在 To tell patient，
//   员工用 Open in WhatsApp 或手机传了，按 Patient told ✓。

import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import * as api from "../api";
import { Badge, Empty, ErrorBox, Loading, Notice, PageHeader, Tabs } from "../components";
import { formatDate, formatDateTime, formatPhone, formatTime, whatsappLink } from "../format";
import { useAction, useLoad } from "../hooks";
import { CopyIcon, RefreshIcon, WhatsAppIcon } from "../icons";
import type { AppointmentRequest, GpisChoice, RequestStatus } from "../types";

type View = RequestStatus | "TO_TELL";

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

/** 确认之后告诉员工：病人收到了没有 */
function confirmedNotice(r: AppointmentRequest): { tone: "success" | "warning"; text: string } {
  if (r.patient_told_at)
    return { tone: "success", text: `${r.customer_name}: confirmed, and the patient was sent the confirmation.` };
  return {
    tone: "warning",
    text: `${r.customer_name}: confirmed, but the patient was not messaged${
      r.notify_problem ? ` (${r.notify_problem})` : ""
    }. Tell the patient from "To tell patient".`,
  };
}

function ChoiceLine({ c }: { c: GpisChoice }) {
  const tags = [c.same_patient && "Same patient", c.same_doctor && "Same doctor", c.same_time && "Same time"].filter(
    Boolean,
  );
  return (
    <span className="choice-text">
      <span className="time">{c.time}</span> {c.patient_name || "(no name)"}{" "}
      <span className="muted">· Dr {c.doctor_name}</span>
      {tags.length > 0 && <span className="choice-tags"> {tags.join(" · ")}</span>}
      {c.used_by_request_id !== null && (
        <span className="muted"> · already confirms request #{c.used_by_request_id}</span>
      )}
    </span>
  );
}

/** 员工按 Entered in GPiS ✓：当场查 GPiS，点选是哪一个预约 */
function ConfirmPanel({
  request,
  onDone,
  onCancel,
}: {
  request: AppointmentRequest;
  onDone: (r: AppointmentRequest) => void;
  onCancel: () => void;
}) {
  const [date, setDate] = useState(request.preferred_date ?? "");
  const [picked, setPicked] = useState<number | null>(null);
  const list = useLoad(
    () => (date ? api.requests.gpis(request.id, date) : Promise.resolve(undefined)),
    [request.id, date],
  );
  const action = useAction();
  const choices = list.data?.choices ?? [];

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (picked === null) return;
    let result: AppointmentRequest | undefined;
    if (await action.run(async () => (result = await api.requests.confirm(request.id, picked, date)))) {
      onDone(result!);
    }
  }

  return (
    <form className="inline-form confirm-form" onSubmit={submit}>
      <p className="small">
        Enter the appointment in GPiS first. Then pick it below: the system checks GPiS again and messages the
        patient the GPiS date, time and doctor.
      </p>
      <div className="confirm-date">
        <label>
          GPiS date
          <input
            type="date"
            value={date}
            onChange={(e) => {
              setDate(e.target.value);
              setPicked(null);
            }}
          />
        </label>
        <button type="button" className="small" onClick={list.reload} disabled={!date || list.loading}>
          <RefreshIcon />
          Read GPiS again
        </button>
      </div>

      {!date ? (
        <p className="muted small">This request has no date: choose the date you booked in GPiS.</p>
      ) : list.data === undefined ? (
        list.loading && <Loading />
      ) : (
        <>
          {!list.data.can_notify && (
            <Notice tone="warning">
              The list comes from {list.data.source}: the patient will not be messaged automatically.
            </Notice>
          )}
          {choices.length === 0 ? (
            <p className="muted small">
              GPiS has no appointments on {formatDate(date)}. Enter it in GPiS first, then press Read GPiS again.
            </p>
          ) : (
            <fieldset className="gpis-choices">
              <legend>Appointments in GPiS on {formatDate(list.data.date)}</legend>
              {choices.map((c) => (
                <label key={c.appointment_id} className={c.same_patient || (c.same_doctor && c.same_time) ? "match" : ""}>
                  <input
                    type="radio"
                    name={`gpis-${request.id}`}
                    value={c.appointment_id}
                    checked={picked === c.appointment_id}
                    disabled={c.used_by_request_id !== null}
                    onChange={() => setPicked(c.appointment_id)}
                  />
                  <ChoiceLine c={c} />
                </label>
              ))}
            </fieldset>
          )}
        </>
      )}

      <ErrorBox message={list.error ?? action.error} onRetry={list.error ? list.reload : undefined} />
      <div className="actions">
        <button type="submit" className="primary" disabled={picked === null || action.busy}>
          Confirm this appointment
        </button>
        <button type="button" onClick={onCancel} disabled={action.busy}>
          Back
        </button>
      </div>
    </form>
  );
}

/** 「要通知」：系统没有发确认消息，员工自己传 */
function TellActions({ request: r, onChanged }: { request: AppointmentRequest; onChanged: () => void }) {
  const [copied, setCopied] = useState(false);
  const action = useAction();
  const canCopy = typeof navigator !== "undefined" && !!navigator.clipboard;

  async function copy() {
    if (!r.confirm_message) return;
    await navigator.clipboard.writeText(r.confirm_message);
    setCopied(true);
  }

  return (
    <>
      <Notice tone="warning">
        Not sent by the system{r.notify_problem ? `: ${r.notify_problem}` : " (the system stopped before sending)"}.
        Tell the patient yourself, then press Patient told.
      </Notice>
      {r.confirm_message && <pre className="message-preview">{r.confirm_message}</pre>}
      <ErrorBox message={action.error} />
      <div className="card-actions actions">
        {r.whatsapp_allowed && r.whatsapp_phone && r.confirm_message && (
          <a className="button primary" href={whatsappLink(r.whatsapp_phone, r.confirm_message)}>
            <WhatsAppIcon />
            Open in WhatsApp
          </a>
        )}
        {canCopy && r.confirm_message && (
          <button type="button" onClick={() => void copy()}>
            <CopyIcon />
            {copied ? "Copied" : "Copy message"}
          </button>
        )}
        <button
          type="button"
          className={r.whatsapp_allowed ? "" : "primary"}
          disabled={action.busy}
          onClick={async () => {
            if (await action.run(() => api.requests.patientTold(r.id))) onChanged();
          }}
        >
          Patient told ✓
        </button>
      </div>
    </>
  );
}

function RequestCard({
  request: r,
  all,
  onChanged,
  onConfirmed,
}: {
  request: AppointmentRequest;
  all: AppointmentRequest[];
  onChanged: () => void;
  onConfirmed: (r: AppointmentRequest) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const action = useAction();
  const mates = groupMates(r, all);
  const toTell = r.status === "CONFIRMED" && r.patient_told_at === null;

  async function change(question: string, fn: (id: number) => Promise<AppointmentRequest>) {
    if (window.confirm(question) && (await action.run(() => fn(r.id)))) onChanged();
  }

  return (
    <li className="card request">
      <div className="card-head">
        <div>
          <strong>{r.customer_name}</strong>
          {r.whatsapp_phone && <div className="phone muted">{formatPhone(r.whatsapp_phone)}</div>}
          <div className="muted small">
            {r.gpis_contact_id ? `GPiS ContactID ${r.gpis_contact_id}` : "Not linked to a GPiS contact"}
          </div>
        </div>
        <Badge kind={toTell ? "pending" : r.status}>{toTell ? "To tell" : STATUS_LABEL[r.status]}</Badge>
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
        {r.confirmed_date && (
          <>
            <dt>In GPiS</dt>
            <dd>
              <strong>
                {formatDate(r.confirmed_date)}
                {r.confirmed_slot && ` ${formatTime(r.confirmed_slot)}`}
                {r.confirmed_doctor_id && ` · Dr ${r.confirmed_doctor_id}`}
              </strong>
            </dd>
          </>
        )}
        {r.gpis_appointment_id !== null && (
          <>
            <dt>GPiS AppointmentID</dt>
            <dd>{r.gpis_appointment_id}</dd>
          </>
        )}
        {r.status === "CONFIRMED" && r.patient_told_at && (
          <>
            <dt>Patient told</dt>
            <dd>
              {formatDateTime(r.patient_told_at)}
              {r.patient_told_by === null ? " (sent by the system)" : " (by staff)"}
            </dd>
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

      {toTell && <TellActions request={r} onChanged={onChanged} />}

      <ErrorBox message={action.error} />

      {confirming ? (
        <ConfirmPanel
          request={r}
          onDone={(result) => {
            setConfirming(false);
            onConfirmed(result);
          }}
          onCancel={() => setConfirming(false)}
        />
      ) : (
        (r.status === "PENDING" || r.status === "CONFIRMED") && (
          <div className="card-actions actions">
            {r.status === "PENDING" && (
              <>
                <button type="button" className="primary" disabled={action.busy} onClick={() => setConfirming(true)}>
                  Entered in GPiS ✓
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
  const [view, setView] = useState<View>("PENDING");
  const [notice, setNotice] = useState<{ tone: "success" | "warning"; text: string } | null>(null);
  const list = useLoad(() => (view === "TO_TELL" ? api.requests.toTell() : api.requests.list(view)), [view], 30_000);
  const toTell = useLoad(() => api.requests.toTell(), [], 30_000);

  function reload() {
    list.reload();
    toTell.reload();
  }

  const tabs: { value: View; label: string }[] = [
    { value: "PENDING", label: "Pending" },
    { value: "TO_TELL", label: toTell.data?.length ? `To tell patient (${toTell.data.length})` : "To tell patient" },
    { value: "CONFIRMED", label: "Confirmed" },
    { value: "REJECTED", label: "Rejected" },
    { value: "CANCELLED", label: "Cancelled" },
  ];

  return (
    <div className="page">
      <PageHeader
        title="Appointment requests"
        description="Booking requests waiting for GPiS. Enter each one in GPiS first, then press Entered in GPiS here."
        actions={
          <button type="button" onClick={reload}>
            <RefreshIcon />
            Refresh
          </button>
        }
      />
      <Tabs
        label="Request status"
        value={view}
        options={tabs}
        onChange={(v) => {
          setView(v);
          setNotice(null);
        }}
      />
      {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}
      <ErrorBox message={list.error} onRetry={list.reload} />
      {list.data === undefined ? (
        list.loading && <Loading />
      ) : list.data.length === 0 ? (
        <Empty>
          {view === "TO_TELL" ? "Every confirmed patient has been told." : `No ${view.toLowerCase()} requests.`}
        </Empty>
      ) : (
        <ul className="cards">
          {list.data.map((r) => (
            <RequestCard
              key={r.id}
              request={r}
              all={list.data ?? []}
              onChanged={reload}
              onConfirmed={(result) => {
                setNotice(confirmedNotice(result));
                reload();
              }}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
