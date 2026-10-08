// 预约提醒（Phase 5b 第一步，docs/architecture.md 第 8 节）：系统从 GPiS 排好名单，员工看过再发。
// - Ready：可以发的，每个号码一张卡；家人合成一条（D49）。
// - Needs staff：不确定的，写明原因，员工自己处理（例：没有 *C、没有手机号码）。
// - Open in WhatsApp（D54）：打开 WhatsApp Desktop 里那位病人的对话、消息已经填好，员工按 Enter 发出。
//   用 whatsapp:// 而不是 wa.me 网址：网址会留在浏览器的历史记录（有号码和名字，D31）。
//   后端说可以（whatsapp_allowed）才显示：读 GPiS_Dev 时没有这个按钮。
// - 每次 Refresh 都重新读 GPiS，不自动更新；这个页面不存任何东西（「按过了」只记在这个画面，重新整理就没了）。

import { useState, type FormEvent } from "react";
import * as api from "../api";
import { Badge, Empty, ErrorBox, Loading, Tabs } from "../components";
import { formatDate, formatDateTime, formatPhone } from "../format";
import { useLoad } from "../hooks";
import type { PhoneKind, ReminderGroup, ReminderList } from "../types";

type View = "READY" | "STAFF" | "OTHER";

const KIND_LABEL: Record<PhoneKind, string | null> = {
  MY_MOBILE: null,
  SG_MOBILE: "Singapore",
  OTHER_COUNTRY: "Overseas",
  LANDLINE: "Landline",
  MISSING: "No number",
};

/** 打开 WhatsApp Desktop 的对话，消息已经填好（D54） */
export function whatsappLink(phone: string, message: string): string {
  return `whatsapp://send?phone=${phone}&text=${encodeURIComponent(message)}`;
}

function names(g: ReminderGroup): string {
  return [...new Set(g.lines.map((l) => l.patient_name))].join(" & ");
}

function Lines({ group, showDate }: { group: ReminderGroup; showDate: boolean }) {
  return (
    <ul className="reminder-lines">
      {group.lines.map((l) => (
        <li key={l.appointment_ids.join(",")}>
          <strong>{l.time ?? "?"}</strong> {l.patient_name} <span className="muted">· Dr {l.doctor_name}</span>
          {showDate && <span className="muted"> · {formatDate(group.date)}</span>}
          {l.status && l.status !== "Confirmed" && <span className="muted"> · {l.status}</span>}
        </li>
      ))}
    </ul>
  );
}

/** 没有号码时不显示（原因已经列在 problems 里） */
function PhoneLine({ group }: { group: ReminderGroup }) {
  if (!group.phone) return null;
  const kind = KIND_LABEL[group.phone_kind];
  return (
    <div className="muted small">
      {formatPhone(group.phone)}
      {kind && (
        <>
          {" "}
          <Badge kind="pending">{kind}</Badge>
        </>
      )}
    </div>
  );
}

function ReadyCard({ group, showDate, production }: { group: ReminderGroup; showDate: boolean; production: boolean }) {
  const [openedAt, setOpenedAt] = useState<Date | null>(null);
  const [copied, setCopied] = useState(false);
  const canCopy = typeof navigator !== "undefined" && !!navigator.clipboard;

  async function copy() {
    if (!group.message) return;
    await navigator.clipboard.writeText(group.message);
    setCopied(true);
  }

  return (
    <li className={openedAt ? "card reminder opened" : "card reminder"}>
      <div className="row-between">
        <div>
          <strong>{names(group)}</strong>
          <PhoneLine group={group} />
        </div>
        {openedAt && <Badge kind="ok">Opened</Badge>}
      </div>
      <Lines group={group} showDate={showDate} />

      {group.message && (
        <details>
          <summary>Message</summary>
          <pre className="message-preview">{group.message}</pre>
        </details>
      )}

      <div className="actions">
        {group.whatsapp_allowed && group.phone && group.message ? (
          <a
            className="button primary"
            href={whatsappLink(group.phone, group.message)}
            onClick={() => setOpenedAt(new Date())}
          >
            {openedAt ? "Open in WhatsApp again" : "Open in WhatsApp"}
          </a>
        ) : (
          <span className="muted small">
            {production ? "Open in WhatsApp is not available for this number." : "Open in WhatsApp is off for this list."}
          </span>
        )}
        {canCopy && group.message && (
          <button type="button" onClick={() => void copy()}>
            {copied ? "Copied" : "Copy message"}
          </button>
        )}
      </div>
      {openedAt && (
        <p className="muted small">
          Opened at {openedAt.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}. Check the message
          in WhatsApp, then press Enter to send it.
        </p>
      )}
    </li>
  );
}

function StaffCard({ group, showDate }: { group: ReminderGroup; showDate: boolean }) {
  return (
    <li className="card reminder">
      <strong>{names(group)}</strong>
      <PhoneLine group={group} />
      <ul className="problems">
        {group.problems.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ul>
      <Lines group={group} showDate={showDate} />
    </li>
  );
}

function Summary({ data }: { data: ReminderList }) {
  const custom = data.dates.join() !== data.suggested_dates.join();
  return (
    <div className="muted small">
      {custom ? "Appointments on " : "Today's reminders: appointments on "}
      {data.dates.map(formatDate).join(", ")} · read from {data.source} at {formatDateTime(data.read_at)}
    </div>
  );
}

export default function RemindersPage() {
  const [date, setDate] = useState<string>("");
  const [draft, setDraft] = useState<string>("");
  const [view, setView] = useState<View>("READY");
  const list = useLoad(() => api.reminders.list(date || undefined), [date]);
  const data = list.data;
  const showDate = (data?.dates.length ?? 0) > 1;
  const otherCount = data?.not_appointments.reduce((n, r) => n + r.count, 0) ?? 0;

  function pick(e: FormEvent) {
    e.preventDefault();
    setDate(draft);
  }

  return (
    <div className="page">
      <div className="row-between">
        <h1>Reminders</h1>
        <button type="button" onClick={list.reload}>
          Refresh
        </button>
      </div>

      <form className="inline" onSubmit={pick}>
        <label>
          Appointment date{" "}
          <input type="date" value={draft} onChange={(e) => setDraft(e.target.value)} />
        </label>
        <button type="submit" disabled={!draft}>
          Show
        </button>
        {date && (
          <button
            type="button"
            className="link"
            onClick={() => {
              setDate("");
              setDraft("");
            }}
          >
            Back to today's reminders
          </button>
        )}
      </form>

      <ErrorBox message={list.error} onRetry={list.reload} />
      {data === undefined ? (
        list.loading && <Loading />
      ) : (
        <>
          <Summary data={data} />
          {!data.production && (
            <p className="note">
              Preview only: this list is read from {data.source}, not the clinic's live GPiS. Open in WhatsApp only
              appears for numbers in WHATSAPP_ALLOWED_RECIPIENTS.
            </p>
          )}
          <Tabs
            label="Reminder lists"
            value={view}
            onChange={setView}
            options={[
              { value: "READY", label: `Ready (${data.ready.length})` },
              { value: "STAFF", label: `Needs staff (${data.needs_staff.length})` },
              { value: "OTHER", label: `Not appointments (${otherCount})` },
            ]}
          />
          {view === "READY" &&
            (data.ready.length === 0 ? (
              <Empty>No reminders to send.</Empty>
            ) : (
              <ul className="cards">
                {data.ready.map((g) => (
                  <ReadyCard key={g.key} group={g} showDate={showDate} production={data.production} />
                ))}
              </ul>
            ))}
          {view === "STAFF" &&
            (data.needs_staff.length === 0 ? (
              <Empty>Nothing needs checking.</Empty>
            ) : (
              <ul className="cards">
                {data.needs_staff.map((g) => (
                  <StaffCard key={g.key} group={g} showDate={showDate} />
                ))}
              </ul>
            ))}
          {view === "OTHER" &&
            (otherCount === 0 ? (
              <Empty>No cancelled appointments, OFF DAY records or 00:00 to-dos.</Empty>
            ) : (
              <ul className="counts">
                {data.not_appointments.map((r) => (
                  <li key={r.reason}>
                    {r.reason}: <strong>{r.count}</strong>
                  </li>
                ))}
              </ul>
            ))}
        </>
      )}
    </div>
  );
}
