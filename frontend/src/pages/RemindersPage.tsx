// 预约提醒（Phase 5b 第一步，docs/architecture.md 第 8 节）：系统从 GPiS 排好名单，员工看过再发。
// - Ready：可以发的，每个号码一张卡；家人合成一条（D49）。
// - Needs staff：不确定的，写明原因，员工自己处理（例：没有 *C、没有手机号码）。
// - Open in WhatsApp（D54）：打开 WhatsApp Desktop 里那位病人的对话、消息已经填好，员工按 Enter 发出。
//   用 whatsapp:// 而不是 wa.me 网址：网址会留在浏览器的历史记录（有号码和名字，D31）。
//   后端说可以（whatsapp_allowed）才显示：读 GPiS_Dev 时没有这个按钮。
//   按了就记在后端（reminders 表）：谁、几点按的；换页、重新整理、另一位员工都看得到，避免同一个号码发两次。
//   系统不知道员工最后有没有按 Enter：按错了可以按 Mark as not sent。
// - NO WA（D55）：病人在签名表写 NO WA → 员工按一次，这个号码（整个号码，家人也一起）以后不提醒。
// - 每次 Refresh 都重新读 GPiS，不自动更新。

import { useEffect, useState, type FormEvent } from "react";
import * as api from "../api";
import { Badge, Empty, ErrorBox, Loading, Tabs } from "../components";
import { formatDate, formatDateTime, formatPhone } from "../format";
import { useAction, useLoad } from "../hooks";
import type { PhoneKind, ReminderGroup, ReminderList, ReminderRecord } from "../types";

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

/** 按过 Open in WhatsApp / 没有发出去：谁、几点 */
function RecordLine({ record }: { record: ReminderRecord }) {
  const who = record.staff_name ? ` by ${record.staff_name}` : "";
  const what = record.status === "OPENED" ? "Opened in WhatsApp" : "Marked as not sent";
  return (
    <p className="muted small">
      {what}
      {who} at {formatDateTime(record.updated_at)}.
      {record.status === "OPENED" && " Check the message in WhatsApp, then press Enter to send it."}
    </p>
  );
}

/** 病人在签名表写 NO WA → 这个号码不要提醒；或改回照常提醒 */
function OptOutButton({ group, onChanged }: { group: ReminderGroup; onChanged: () => void }) {
  const action = useAction();
  if (!group.phone) return null;
  const phone = formatPhone(group.phone);
  const stop = !group.opted_out;
  async function toggle() {
    const question = stop
      ? `Stop reminders for ${phone}? Everyone who uses this number will stop getting reminders (patient wrote NO WA).`
      : `Send reminders to ${phone} again?`;
    if (window.confirm(question) && (await action.run(() => api.reminders.optOut(group.phone!, stop)))) onChanged();
  }
  return (
    <>
      <button type="button" className="link" disabled={action.busy} onClick={() => void toggle()}>
        {stop ? "NO WA: stop reminders" : "Allow reminders again"}
      </button>
      <ErrorBox message={action.error} />
    </>
  );
}

function ReadyCard({
  group,
  showDate,
  production,
  onChanged,
}: {
  group: ReminderGroup;
  showDate: boolean;
  production: boolean;
  onChanged: () => void;
}) {
  // 后端回来的最新状态；名单重新读了就用名单上的
  const [saved, setSaved] = useState<ReminderRecord | null>(null);
  useEffect(() => setSaved(null), [group.record]);
  const record = saved ?? group.record;
  const opened = record?.status === "OPENED";
  const [copied, setCopied] = useState(false);
  const action = useAction();
  const canCopy = typeof navigator !== "undefined" && !!navigator.clipboard;

  async function copy() {
    if (!group.message) return;
    await navigator.clipboard.writeText(group.message);
    setCopied(true);
  }

  // 连结照常打开 WhatsApp；同时记在后端（失败的话显示错误，WhatsApp 那边还是打开了）
  function recordOpened() {
    void action.run(async () => setSaved(await api.reminders.opened(group.date, group.phone!)));
  }

  function markNotSent() {
    void action.run(async () => setSaved(await api.reminders.notSent(group.date, group.phone!)));
  }

  return (
    <li className={opened ? "card reminder opened" : "card reminder"}>
      <div className="row-between">
        <div>
          <strong>{names(group)}</strong>
          <PhoneLine group={group} />
        </div>
        {opened && <Badge kind="ok">Opened</Badge>}
        {record?.status === "NOT_SENT" && <Badge kind="pending">Not sent</Badge>}
      </div>
      <Lines group={group} showDate={showDate} />

      {group.message && (
        <details>
          <summary>Message</summary>
          <pre className="message-preview">{group.message}</pre>
        </details>
      )}

      {opened && record?.changed && (
        <p className="note">
          GPiS changed after this was opened (an appointment was added or removed). Check the list, then open it
          again if the patient needs the new message.
        </p>
      )}

      <div className="actions">
        {group.whatsapp_allowed && group.phone && group.message ? (
          <a className="button primary" href={whatsappLink(group.phone, group.message)} onClick={recordOpened}>
            {opened ? "Open in WhatsApp again" : "Open in WhatsApp"}
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
        {opened && (
          <button type="button" disabled={action.busy} onClick={markNotSent}>
            Mark as not sent
          </button>
        )}
        <OptOutButton group={group} onChanged={onChanged} />
      </div>
      {record && <RecordLine record={record} />}
      <ErrorBox message={action.error} />
    </li>
  );
}

function StaffCard({ group, showDate, onChanged }: { group: ReminderGroup; showDate: boolean; onChanged: () => void }) {
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
      {group.phone && (
        <div className="actions">
          <OptOutButton group={group} onChanged={onChanged} />
        </div>
      )}
      {group.record && <RecordLine record={group.record} />}
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
          {view === "READY" && data.ready.length > 0 && (
            <p className="muted small">
              Opened in WhatsApp: {data.ready.filter((g) => g.record?.status === "OPENED").length} of{" "}
              {data.ready.length}
            </p>
          )}
          {view === "READY" &&
            (data.ready.length === 0 ? (
              <Empty>No reminders to send.</Empty>
            ) : (
              <ul className="cards">
                {data.ready.map((g) => (
                  <ReadyCard
                    key={g.key}
                    group={g}
                    showDate={showDate}
                    production={data.production}
                    onChanged={list.reload}
                  />
                ))}
              </ul>
            ))}
          {view === "STAFF" &&
            (data.needs_staff.length === 0 ? (
              <Empty>Nothing needs checking.</Empty>
            ) : (
              <ul className="cards">
                {data.needs_staff.map((g) => (
                  <StaffCard key={g.key} group={g} showDate={showDate} onChanged={list.reload} />
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
