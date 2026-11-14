// 预约提醒（Phase 5b 第一步，docs/architecture.md 第 8 节）：系统从 GPiS 排好名单，员工看过再发。
// - Ready：可以发的，每个号码一张卡片（一排 3 张）；家人合成一条（D49）。
// - Needs staff：不确定的，写明原因，员工自己处理（例：没有 *C、没有手机号码）。
// - Open in WhatsApp（D54）：打开 WhatsApp Desktop 里那位病人的对话、消息已经填好，员工按 Enter 发出。
//   用 whatsapp:// 而不是 wa.me 网址：网址会留在浏览器的历史记录（有号码和名字，D31）。
//   后端说可以（whatsapp_allowed）才显示：读 GPiS_Dev 时没有这个按钮。
//   按了就记在后端（reminders 表）：谁、几点按的；换页、重新整理、另一位员工都看得到，避免同一个号码发两次。
//   系统不知道员工最后有没有按 Enter：按错了可以按 Mark as not sent。
// - NO WA（D55）：病人在签名表写 NO WA → 员工按一次，这个号码（整个号码，家人也一起）以后不提醒。
// - Extra note（D82）：每条消息最后加的一段话（例 Feel free to pay cash），上面的按钮开弹出视窗改；改了重新读名单，消息跟着变。
//   已经按过 Open in WhatsApp 的不会变（WhatsApp 那边已经填好了）。
// - 每次 Refresh 都重新读 GPiS，不自动更新。
// - 画面用 shadcn/ui（D83，第一个换过去的页面）：src/components/ui/；页面上面的标题（PageHeader）和其他页面共用。

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import {
  CheckIcon,
  CopyIcon,
  InboxIcon,
  InfoIcon,
  LoaderCircleIcon,
  MessageSquareTextIcon,
  PencilIcon,
  RefreshCwIcon,
  TriangleAlertIcon,
} from "lucide-react";
import * as api from "../api";
import { Modal, Page, PageHeader } from "../components";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { CARD_GRID, CARD_ROWS_3, CARD_ROWS_4, Card, CardAction, CardContent, CardFooter, CardHeader, CardTitle } from "../components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Progress } from "../components/ui/progress";
import { cn } from "../lib/utils";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Textarea } from "../components/ui/textarea";
import { formatDate, formatDateTime, formatPhone, whatsappLink } from "../format";
import { useAction, useLoad } from "../hooks";
import { WhatsAppIcon } from "../icons";
import type { PhoneKind, ReminderGroup, ReminderList, ReminderNote, ReminderRecord } from "../types";

type View = "READY" | "STAFF" | "OTHER";

const NOTE_MAX = 500; // 和后端 REMINDER_NOTE_MAX 一样

const KIND_LABEL: Record<PhoneKind, string | null> = {
  MY_MOBILE: null,
  SG_MOBILE: "Singapore",
  OTHER_COUNTRY: "Overseas",
  LANDLINE: "Landline",
  MISSING: "No number",
};

export { whatsappLink };

function names(g: ReminderGroup): string {
  return [...new Set(g.lines.map((l) => l.patient_name))].join(" & ");
}

/** 出错（role=alert）；onRetry 给了就多一个 Try again */
function ErrorAlert({ message, onRetry }: { message: string | null; onRetry?: () => void }) {
  if (!message) return null;
  return (
    <Alert variant="destructive">
      <TriangleAlertIcon />
      <AlertDescription className="flex flex-wrap items-center gap-x-3">
        <span>{message}</span>
        {onRetry && (
          <Button type="button" variant="link" size="sm" onClick={onRetry}>
            Try again
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}

function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed bg-card px-6 py-12 text-center text-sm text-muted-foreground">
      <InboxIcon className="size-7" aria-hidden="true" />
      <p>{children}</p>
    </div>
  );
}

function LoadingState() {
  return (
    <p className="flex items-center gap-2 text-sm text-muted-foreground">
      <LoaderCircleIcon className="size-4 animate-spin" aria-hidden="true" />
      Loading…
    </p>
  );
}

function Lines({ group, showDate }: { group: ReminderGroup; showDate: boolean }) {
  return (
    <ul className="m-0 flex list-none flex-col gap-1.5 rounded-lg bg-muted p-3 text-sm">
      {group.lines.map((l) => (
        <li key={l.appointment_ids.join(",")} className="flex gap-3">
          <span className="w-11 shrink-0 font-semibold tabular-nums">{l.time ?? "?"}</span>
          <span className="min-w-0">
            {l.patient_name} <span className="text-muted-foreground">· Dr {l.doctor_name}</span>
            {showDate && <span className="text-muted-foreground"> · {formatDate(group.date)}</span>}
            {l.status && l.status !== "Confirmed" && <span className="text-muted-foreground"> · {l.status}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** 卡片上面：名字、号码（没有号码时不显示号码，原因已经列在 problems 里）、右边的状态 */
function CardTop({ group, status }: { group: ReminderGroup; status?: ReactNode }) {
  const kind = KIND_LABEL[group.phone_kind];
  return (
    <CardHeader>
      <CardTitle>
        <strong className="font-semibold">{names(group)}</strong>
      </CardTitle>
      {group.phone && (
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground tabular-nums">
          {formatPhone(group.phone)}
          {kind && <Badge variant="warning">{kind}</Badge>}
        </div>
      )}
      {status && <CardAction>{status}</CardAction>}
    </CardHeader>
  );
}

function StatusBadge({ record }: { record: ReminderRecord | null }) {
  if (record?.status === "OPENED")
    return (
      <Badge variant="success">
        <CheckIcon />
        Opened
      </Badge>
    );
  if (record?.status === "NOT_SENT") return <Badge variant="warning">Not sent</Badge>;
  return <Badge variant="secondary">To send</Badge>;
}

/** 按过 Open in WhatsApp / 没有发出去：谁、几点 */
function RecordLine({ record }: { record: ReminderRecord }) {
  const who = record.staff_name ? ` by ${record.staff_name}` : "";
  const what = record.status === "OPENED" ? "Opened in WhatsApp" : "Marked as not sent";
  return (
    <p className="text-xs text-muted-foreground">
      {what}
      {who} at {formatDateTime(record.updated_at)}.
      {record.status === "OPENED" && " Check the message in WhatsApp, then press Enter to send it."}
    </p>
  );
}

/** 卡片最下面：Message（按了在画面中间弹出视窗，看整条消息）+ 右边的 NO WA。卡片本身不会变高 */
function MessageFooter({ title, message, children }: { title: string; message: string | null; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const canCopy = typeof navigator !== "undefined" && !!navigator.clipboard;
  if (!message) return <CardFooter className="items-start justify-end border-t pt-4">{children}</CardFooter>;

  async function copy() {
    await navigator.clipboard.writeText(message!);
    setCopied(true);
  }

  return (
    <CardFooter className="flex-wrap items-start gap-2 border-t pt-4">
      <Button type="button" variant="link" size="sm" className="text-sm" onClick={() => setOpen(true)}>
        <MessageSquareTextIcon />
        Message
      </Button>
      {children}
      {open && (
        <Modal
          title={`Message – ${title}`}
          subtitle="The reminder exactly as it will be filled in WhatsApp."
          onClose={() => {
            setOpen(false);
            setCopied(false);
          }}
          footer={
            <>
              {canCopy && (
                <Button type="button" variant="outline" onClick={() => void copy()}>
                  {copied ? <CheckIcon /> : <CopyIcon />}
                  {copied ? "Copied" : "Copy message"}
                </Button>
              )}
              <Button type="button" onClick={() => setOpen(false)}>
                Done
              </Button>
            </>
          }
        >
          <pre
            aria-label="Reminder message"
            className="m-0 max-h-[60vh] overflow-y-auto rounded-lg border bg-muted p-3 font-sans text-sm leading-relaxed whitespace-pre-wrap"
          >
            {message}
          </pre>
        </Modal>
      )}
    </CardFooter>
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
    <div className="ml-auto flex flex-col items-end gap-1">
      <Button
        type="button"
        size="sm"
        variant={stop ? "ghost-destructive" : "outline"}
        disabled={action.busy}
        onClick={() => void toggle()}
      >
        {stop ? "NO WA: stop reminders" : "Allow reminders again"}
      </Button>
      <ErrorAlert message={action.error} />
    </div>
  );
}

function ReadyCard({
  group,
  record,
  showDate,
  production,
  onChanged,
  onRecorded,
}: {
  group: ReminderGroup;
  record: ReminderRecord | null;
  showDate: boolean;
  production: boolean;
  onChanged: () => void;
  onRecorded: (key: string, record: ReminderRecord) => void;
}) {
  const opened = record?.status === "OPENED";
  const [copied, setCopied] = useState(false);
  const action = useAction();
  const canCopy = typeof navigator !== "undefined" && !!navigator.clipboard;

  async function copy() {
    if (!group.message) return;
    await navigator.clipboard.writeText(group.message);
    setCopied(true);
  }

  // 连结照常打开 WhatsApp；同时记在后端（失败的话显示错误，WhatsApp 那边还是打开了）。
  // 后端回来的结果交给页面记着（onRecorded）：上面的「Opened in WhatsApp: x of y」马上更新，切分页回来也还在
  function recordOpened() {
    void action.run(async () => onRecorded(group.key, await api.reminders.opened(group.date, group.phone!)));
  }

  function markNotSent() {
    void action.run(async () => onRecorded(group.key, await api.reminders.notSent(group.date, group.phone!)));
  }

  return (
    <li className={CARD_ROWS_4}>
      <Card className={cn(CARD_ROWS_4, opened && "border-success-border bg-success-bg/40")}>
        <CardTop group={group} status={<StatusBadge record={record} />} />

        <CardContent className="flex flex-col gap-3">
          <Lines group={group} showDate={showDate} />

          {opened && record?.changed && (
            <Alert variant="warning" role="status">
              <TriangleAlertIcon />
              <AlertDescription>
                GPiS changed after this was opened (an appointment was added or removed). Check the list, then open
                it again if the patient needs the new message.
              </AlertDescription>
            </Alert>
          )}
        </CardContent>

        <CardContent className="flex flex-col gap-2">
            {group.whatsapp_allowed && group.phone && group.message ? (
              <Button asChild className="w-full">
                <a href={whatsappLink(group.phone, group.message)} onClick={recordOpened}>
                  <WhatsAppIcon />
                  {opened ? "Open in WhatsApp again" : "Open in WhatsApp"}
                </a>
              </Button>
            ) : (
              <p className="text-sm text-muted-foreground">
                {production
                  ? "Open in WhatsApp is not available for this number."
                  : "Open in WhatsApp is off for this list."}
              </p>
            )}
            {((canCopy && group.message) || opened) && (
              <div className="flex gap-2 *:flex-1">
                {canCopy && group.message && (
                  <Button type="button" variant="outline" size="sm" onClick={() => void copy()}>
                    {copied ? <CheckIcon /> : <CopyIcon />}
                    {copied ? "Copied" : "Copy message"}
                  </Button>
                )}
                {opened && (
                  <Button type="button" variant="outline" size="sm" disabled={action.busy} onClick={markNotSent}>
                    Mark as not sent
                  </Button>
                )}
              </div>
            )}
            {record && <RecordLine record={record} />}
            <ErrorAlert message={action.error} />
        </CardContent>

        <MessageFooter title={names(group)} message={group.message}>
          <OptOutButton group={group} onChanged={onChanged} />
        </MessageFooter>
      </Card>
    </li>
  );
}

function StaffCard({ group, showDate, onChanged }: { group: ReminderGroup; showDate: boolean; onChanged: () => void }) {
  return (
    <li className={CARD_ROWS_3}>
      <Card className={CARD_ROWS_3}>
        <CardTop group={group} />
        <CardContent className="flex flex-col gap-3">
          <Lines group={group} showDate={showDate} />
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-sm text-warning">
            {group.problems.map((p) => (
              <li key={p} className="flex items-start gap-2">
                <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                {p}
              </li>
            ))}
          </ul>
        </CardContent>
        {/* 最下面一行每张卡片都有（和旁边的卡片对齐）；没有号码时写一句，不放 NO WA */}
        <CardFooter className="flex-wrap items-start gap-2 border-t pt-4">
          {group.record && (
            <div className="flex-1">
              <RecordLine record={group.record} />
            </div>
          )}
          {group.phone ? (
            <OptOutButton group={group} onChanged={onChanged} />
          ) : (
            !group.record && <p className="py-1.5 text-xs text-muted-foreground">No WhatsApp number to stop.</p>
          )}
        </CardFooter>
      </Card>
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

function OpenedProgress({ data, recorded }: { data: ReminderList; recorded: Record<string, ReminderRecord> }) {
  const opened = data.ready.filter((g) => (recorded[g.key] ?? g.record)?.status === "OPENED").length;
  const total = data.ready.length;
  return (
    <div className="flex min-w-56 items-center gap-3">
      <span className="text-sm whitespace-nowrap text-muted-foreground">
        Opened in WhatsApp: {opened} of {total}
      </span>
      <Progress value={total ? (opened / total) * 100 : 0} aria-label="Opened in WhatsApp" className="w-32" />
    </div>
  );
}

/** 名单上第一条消息，拿掉已经存的那段话 = 预览用的原来的消息（后端是「消息 + 空一行 + 那段话」） */
export function previewBase(data: ReminderList): string | null {
  const message = [...data.ready, ...data.needs_staff].find((g) => g.message)?.message ?? null;
  const saved = data.note.text;
  if (message && saved && message.endsWith(`\n\n${saved}`)) return message.slice(0, -(saved.length + 2));
  return message;
}

/** 预览：原来的消息 + 空一行 + 正在打的那段话（和后端一样，前后空白不算） */
export function withNote(base: string, draft: string): string {
  const note = draft
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((l) => l.trimEnd())
    .join("\n")
    .trim();
  return note ? `${base}\n\n${note}` : base;
}

/** 每条消息最后加的一段话（D82）：页面上面一个按钮，按了开弹出视窗看、改、拿掉。每位员工都能改 */
function NoteButton({ data, onSaved }: { data: ReminderList; onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const note = data.note;
  return (
    <>
      <Button type="button" variant="outline" onClick={() => setOpen(true)}>
        <PencilIcon />
        Extra note
        {note.text && <Badge variant="success">On</Badge>}
      </Button>
      {open && (
        <NoteDialog
          note={note}
          base={previewBase(data)}
          onClose={() => setOpen(false)}
          onSaved={() => {
            setOpen(false);
            onSaved();
          }}
        />
      )}
    </>
  );
}

function NoteDialog({
  note,
  base,
  onClose,
  onSaved,
}: {
  note: ReminderNote;
  base: string | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [draft, setDraft] = useState(note.text ?? "");
  const action = useAction();
  // 预览拉到最下面：那段话在消息最后，打字时要看得到
  const previewRef = useRef<HTMLPreElement>(null);
  useEffect(() => {
    if (previewRef.current) previewRef.current.scrollTop = previewRef.current.scrollHeight;
  }, [draft]);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (await action.run(() => api.reminders.setNote(draft))) onSaved();
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !action.busy) onClose();
      }}
    >
      <DialogContent className="sm:max-w-xl">
        <form className="flex flex-col gap-5" onSubmit={(e) => void save(e)}>
          <DialogHeader>
            <DialogTitle>Extra note</DialogTitle>
            <DialogDescription>
              Added at the end of every reminder message, e.g. "Feel free to pay cash".
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-2">
            <Label htmlFor="reminder-note" className="sr-only">
              Note
            </Label>
            <Textarea
              id="reminder-note"
              aria-label="Note"
              rows={4}
              value={draft}
              maxLength={NOTE_MAX}
              placeholder="Feel free to pay cash 💵"
              onChange={(e) => setDraft(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              {draft.length} / {NOTE_MAX} characters. Leave it empty to add nothing. Reminders already opened in
              WhatsApp do not change.
            </p>
            {note.updated_at && (
              <p className="text-xs text-muted-foreground">
                Last changed{note.staff_name ? ` by ${note.staff_name}` : ""} at {formatDateTime(note.updated_at)}.
              </p>
            )}
            <ErrorAlert message={action.error} />
          </div>

          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Preview</h3>
            {base ? (
              <>
                <p className="text-xs text-muted-foreground">
                  The first message on this list, with the note as typed above. Not saved yet.
                </p>
                <pre
                  ref={previewRef}
                  aria-label="Message preview"
                  className="m-0 max-h-72 overflow-y-auto rounded-lg border bg-muted p-3 font-sans text-sm leading-relaxed whitespace-pre-wrap"
                >
                  {withNote(base, draft)}
                </pre>
              </>
            ) : (
              <p className="text-xs text-muted-foreground">
                No message on this list to preview. The note goes after the last line, "… See you!", after one empty
                line.
              </p>
            )}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" disabled={action.busy} onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={action.busy}>
              Save note
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function TabCount({ n }: { n: number }) {
  return (
    <Badge variant="secondary" className="min-w-5 rounded-full px-1.5 tabular-nums">
      {n}
    </Badge>
  );
}

export default function RemindersPage() {
  const [date, setDate] = useState<string>("");
  const [draft, setDraft] = useState<string>("");
  const [view, setView] = useState<View>("READY");
  const list = useLoad(() => api.reminders.list(date || undefined), [date]);
  const data = list.data;
  // 这一页按过的（还没重新读名单之前）；重新读了就用名单上的。
  // 放在页面、不放在卡片里：切分页时卡片会拿掉再重新建立，放在卡片里的会不见、又显示成 To send
  const [recorded, setRecorded] = useState<Record<string, ReminderRecord>>({});
  useEffect(() => setRecorded({}), [data]);
  const showDate = (data?.dates.length ?? 0) > 1;
  const otherCount = data?.not_appointments.reduce((n, r) => n + r.count, 0) ?? 0;

  function pick(e: FormEvent) {
    e.preventDefault();
    setDate(draft);
  }

  return (
    <Page>
      <PageHeader
        title="Reminders"
        description={data ? <Summary data={data} /> : "Appointments from GPiS, ready to send on WhatsApp."}
        actions={
          <div className="flex flex-wrap items-end gap-2">
            <form className="flex items-end gap-2" onSubmit={pick}>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="reminder-date" className="text-muted-foreground">
                  Appointment date
                </Label>
                <Input
                  id="reminder-date"
                  type="date"
                  className="w-40"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                />
              </div>
              <Button type="submit" variant="outline" disabled={!draft}>
                Show
              </Button>
            </form>
            {data && <NoteButton data={data} onSaved={list.reload} />}
            <Button type="button" variant="outline" onClick={list.reload}>
              <RefreshCwIcon className={list.loading ? "animate-spin" : undefined} />
              Refresh
            </Button>
          </div>
        }
      />

      {date && (
        <div className="-mt-2">
          <Button
            type="button"
            variant="link"
            size="sm"
            onClick={() => {
              setDate("");
              setDraft("");
            }}
          >
            Back to today's reminders
          </Button>
        </div>
      )}

      <ErrorAlert message={list.error} onRetry={list.reload} />
      {data === undefined ? (
        list.loading && <LoadingState />
      ) : (
        <>
          {!data.production && (
            <Alert variant="warning" role="status">
              <TriangleAlertIcon />
              <AlertDescription>
                Preview only: this list is read from {data.source}, not the clinic's live GPiS. Open in WhatsApp only
                appears for numbers in WHATSAPP_ALLOWED_RECIPIENTS.
              </AlertDescription>
            </Alert>
          )}

          <Tabs value={view} onValueChange={(v) => setView(v as View)}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <TabsList aria-label="Reminder lists">
                <TabsTrigger value="READY">
                  Ready <TabCount n={data.ready.length} />
                </TabsTrigger>
                <TabsTrigger value="STAFF">
                  Needs staff <TabCount n={data.needs_staff.length} />
                </TabsTrigger>
                <TabsTrigger value="OTHER">
                  Not appointments <TabCount n={otherCount} />
                </TabsTrigger>
              </TabsList>
              {view === "READY" && data.ready.length > 0 && <OpenedProgress data={data} recorded={recorded} />}
            </div>

            <TabsContent value="READY">
              {data.ready.length === 0 ? (
                <EmptyState>No reminders to send.</EmptyState>
              ) : (
                <ul className={CARD_GRID}>
                  {data.ready.map((g) => (
                    <ReadyCard
                      key={g.key}
                      group={g}
                      record={recorded[g.key] ?? g.record}
                      showDate={showDate}
                      production={data.production}
                      onChanged={list.reload}
                      onRecorded={(key, record) => setRecorded((r) => ({ ...r, [key]: record }))}
                    />
                  ))}
                </ul>
              )}
            </TabsContent>

            <TabsContent value="STAFF" className="flex flex-col gap-3">
              {data.needs_staff.length === 0 ? (
                <EmptyState>Nothing needs checking.</EmptyState>
              ) : (
                <>
                  <p className="flex items-center gap-2 text-sm text-muted-foreground">
                    <InfoIcon className="size-4" aria-hidden="true" />
                    These are not sent from here. Check each one and remind the patient the usual way if needed.
                  </p>
                  <ul className={CARD_GRID}>
                    {data.needs_staff.map((g) => (
                      <StaffCard key={g.key} group={g} showDate={showDate} onChanged={list.reload} />
                    ))}
                  </ul>
                </>
              )}
            </TabsContent>

            <TabsContent value="OTHER" className="flex flex-col gap-3">
              {otherCount === 0 ? (
                <EmptyState>No cancelled appointments, OFF DAY records or 00:00 to-dos.</EmptyState>
              ) : (
                <>
                  <p className="flex items-center gap-2 text-sm text-muted-foreground">
                    <InfoIcon className="size-4" aria-hidden="true" />
                    Shown as numbers only. No reminder is needed for these.
                  </p>
                  <Card className="max-w-md gap-0 py-1">
                    <ul className="m-0 list-none divide-y p-0">
                      {data.not_appointments.map((r) => (
                        <li key={r.reason} className="flex items-center justify-between px-5 py-3 text-sm">
                          <span>{r.reason}</span>
                          <strong className="font-semibold tabular-nums">{r.count}</strong>
                        </li>
                      ))}
                    </ul>
                  </Card>
                </>
              )}
            </TabsContent>
          </Tabs>
        </>
      )}
    </Page>
  );
}
