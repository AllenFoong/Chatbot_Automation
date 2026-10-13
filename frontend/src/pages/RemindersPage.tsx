// 预约提醒（Phase 5b 第一步，docs/architecture.md 第 8 节）：系统从 GPiS 排好名单，员工看过再发。
// - Ready：可以发的，每个号码一行；家人合成一条（D49）。
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
import { Badge, Empty, ErrorBox, Loading, Notice, PageHeader, Tabs } from "../components";
import { formatDate, formatDateTime, formatPhone } from "../format";
import { useAction, useLoad } from "../hooks";
import { AlertIcon, CopyIcon, RefreshIcon, WhatsAppIcon } from "../icons";
import type { PhoneKind, ReminderGroup, ReminderList, ReminderRecord, ReminderStatus } from "../types";

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
          <span className="time">{l.time ?? "?"}</span>
          <span className="who">
            {l.patient_name} <span className="muted">· Dr {l.doctor_name}</span>
            {showDate && <span className="muted"> · {formatDate(group.date)}</span>}
            {l.status && l.status !== "Confirmed" && <span className="muted"> · {l.status}</span>}
          </span>
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
    <div className="phone muted">
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
    <p className="record muted small">
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
    <div className="opt-out">
      <button
        type="button"
        className={stop ? "ghost small danger-text" : "ghost small"}
        disabled={action.busy}
        onClick={() => void toggle()}
      >
        {stop ? "NO WA: stop reminders" : "Allow reminders again"}
      </button>
      <ErrorBox message={action.error} />
    </div>
  );
}

function ReadyRow({
  group,
  showDate,
  production,
  onChanged,
  onRecorded,
}: {
  group: ReminderGroup;
  showDate: boolean;
  production: boolean;
  onChanged: () => void;
  onRecorded: (key: string, status: ReminderStatus) => void;
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

  function keep(r: ReminderRecord) {
    setSaved(r);
    onRecorded(group.key, r.status); // 上面的「Opened in WhatsApp: x of y」马上更新
  }

  // 连结照常打开 WhatsApp；同时记在后端（失败的话显示错误，WhatsApp 那边还是打开了）
  function recordOpened() {
    void action.run(async () => keep(await api.reminders.opened(group.date, group.phone!)));
  }

  function markNotSent() {
    void action.run(async () => keep(await api.reminders.notSent(group.date, group.phone!)));
  }

  return (
    <li className={opened ? "reminder opened" : "reminder"}>
      <div className="reminder-main">
        <div className="reminder-who">
          <strong>{names(group)}</strong>
          <PhoneLine group={group} />
        </div>
        <Lines group={group} showDate={showDate} />
        <div className="reminder-state">
          {opened && <Badge kind="ok">Opened</Badge>}
          {record?.status === "NOT_SENT" && <Badge kind="pending">Not sent</Badge>}
          {!record && <Badge kind="idle">To send</Badge>}
        </div>
      </div>

      {opened && record?.changed && (
        <Notice tone="warning">
          GPiS changed after this was opened (an appointment was added or removed). Check the list, then open it
          again if the patient needs the new message.
        </Notice>
      )}

      <div className="reminder-actions">
        <div className="actions">
          {group.whatsapp_allowed && group.phone && group.message ? (
            <a className="button primary" href={whatsappLink(group.phone, group.message)} onClick={recordOpened}>
              <WhatsAppIcon />
              {opened ? "Open in WhatsApp again" : "Open in WhatsApp"}
            </a>
          ) : (
            <span className="muted small">
              {production ? "Open in WhatsApp is not available for this number." : "Open in WhatsApp is off for this list."}
            </span>
          )}
          {canCopy && group.message && (
            <button type="button" onClick={() => void copy()}>
              <CopyIcon />
              {copied ? "Copied" : "Copy message"}
            </button>
          )}
          {opened && (
            <button type="button" disabled={action.busy} onClick={markNotSent}>
              Mark as not sent
            </button>
          )}
        </div>
        <OptOutButton group={group} onChanged={onChanged} />
      </div>

      {(group.message || record) && (
        <div className="reminder-meta">
          {group.message && (
            <details>
              <summary>Message</summary>
              <pre className="message-preview">{group.message}</pre>
            </details>
          )}
          {record && <RecordLine record={record} />}
        </div>
      )}
      <ErrorBox message={action.error} />
    </li>
  );
}

function StaffRow({ group, showDate, onChanged }: { group: ReminderGroup; showDate: boolean; onChanged: () => void }) {
  return (
    <li className="reminder needs-staff">
      <div className="reminder-main">
        <div className="reminder-who">
          <strong>{names(group)}</strong>
          <PhoneLine group={group} />
        </div>
        <Lines group={group} showDate={showDate} />
        <ul className="problems">
          {group.problems.map((p) => (
            <li key={p}>
              <AlertIcon size={16} />
              {p}
            </li>
          ))}
        </ul>
      </div>
      {(group.phone || group.record) && (
        <div className="reminder-actions">
          {group.record ? <RecordLine record={group.record} /> : <span />}
          <OptOutButton group={group} onChanged={onChanged} />
        </div>
      )}
    </li>
  );
}

function Summary({ data }: { data: ReminderList }) {
  const custom = data.dates.join() !== data.suggested_dates.join();
  return (
    <p>
      {custom ? "Appointments on " : "Today's reminders: appointments on "}
      {data.dates.map(formatDate).join(", ")} · read from {data.source} at {formatDateTime(data.read_at)}
    </p>
  );
}

function Progress({ data, recorded }: { data: ReminderList; recorded: Record<string, ReminderStatus> }) {
  const opened = data.ready.filter((g) => (recorded[g.key] ?? g.record?.status) === "OPENED").length;
  const total = data.ready.length;
  return (
    <div className="progress">
      <span className="small">
        Opened in WhatsApp: {opened} of {total}
      </span>
      <span className="progress-bar" aria-hidden="true">
        <span style={{ width: `${total ? (opened / total) * 100 : 0}%` }} />
      </span>
    </div>
  );
}

export default function RemindersPage() {
  const [date, setDate] = useState<string>("");
  const [draft, setDraft] = useState<string>("");
  const [view, setView] = useState<View>("READY");
  const list = useLoad(() => api.reminders.list(date || undefined), [date]);
  const data = list.data;
  // 这一页按过的（还没重新读名单之前）；重新读了就用名单上的
  const [recorded, setRecorded] = useState<Record<string, ReminderStatus>>({});
  useEffect(() => setRecorded({}), [data]);
  const showDate = (data?.dates.length ?? 0) > 1;
  const otherCount = data?.not_appointments.reduce((n, r) => n + r.count, 0) ?? 0;

  function pick(e: FormEvent) {
    e.preventDefault();
    setDate(draft);
  }

  return (
    <div className="page">
      <PageHeader
        title="Reminders"
        description={data ? <Summary data={data} /> : "Appointments from GPiS, ready to send on WhatsApp."}
        actions={
          <>
            <form className="date-picker" onSubmit={pick}>
              <label>
                Appointment date{" "}
                <input type="date" value={draft} onChange={(e) => setDraft(e.target.value)} />
              </label>
              <button type="submit" disabled={!draft}>
                Show
              </button>
            </form>
            <button type="button" onClick={list.reload}>
              <RefreshIcon />
              Refresh
            </button>
          </>
        }
      />

      {date && (
        <p className="back-link">
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
        </p>
      )}

      <ErrorBox message={list.error} onRetry={list.reload} />
      {data === undefined ? (
        list.loading && <Loading />
      ) : (
        <>
          {!data.production && (
            <Notice tone="warning">
              Preview only: this list is read from {data.source}, not the clinic's live GPiS. Open in WhatsApp only
              appears for numbers in WHATSAPP_ALLOWED_RECIPIENTS.
            </Notice>
          )}
          <div className="list-toolbar">
            <Tabs
              label="Reminder lists"
              value={view}
              onChange={setView}
              options={[
                { value: "READY", label: "Ready", count: data.ready.length },
                { value: "STAFF", label: "Needs staff", count: data.needs_staff.length },
                { value: "OTHER", label: "Not appointments", count: otherCount },
              ]}
            />
            {view === "READY" && data.ready.length > 0 && <Progress data={data} recorded={recorded} />}
          </div>
          {view === "READY" &&
            (data.ready.length === 0 ? (
              <Empty>No reminders to send.</Empty>
            ) : (
              <ul className="reminder-list">
                {data.ready.map((g) => (
                  <ReadyRow
                    key={g.key}
                    group={g}
                    showDate={showDate}
                    production={data.production}
                    onChanged={list.reload}
                    onRecorded={(key, status) => setRecorded((r) => ({ ...r, [key]: status }))}
                  />
                ))}
              </ul>
            ))}
          {view === "STAFF" &&
            (data.needs_staff.length === 0 ? (
              <Empty>Nothing needs checking.</Empty>
            ) : (
              <>
                <p className="muted small">
                  These are not sent from here. Check each one and remind the patient the usual way if needed.
                </p>
                <ul className="reminder-list">
                  {data.needs_staff.map((g) => (
                    <StaffRow key={g.key} group={g} showDate={showDate} onChanged={list.reload} />
                  ))}
                </ul>
              </>
            ))}
          {view === "OTHER" &&
            (otherCount === 0 ? (
              <Empty>No cancelled appointments, OFF DAY records or 00:00 to-dos.</Empty>
            ) : (
              <>
                <p className="muted small">Shown as numbers only. No reminder is needed for these.</p>
                <ul className="counts">
                  {data.not_appointments.map((r) => (
                    <li key={r.reason}>
                      {r.reason}: <strong>{r.count}</strong>
                    </li>
                  ))}
                </ul>
              </>
            ))}
        </>
      )}
    </div>
  );
}
