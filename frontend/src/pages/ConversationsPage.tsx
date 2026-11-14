// 对话：左边列表，右边打开的那一段（网址 /conversations/12）。
// 员工可以接手（AI 停止回复）、交回 AI、结束对话、回复病人（docs/architecture.md 第 5 节）。
// 回复经 WhatsApp 真的发出去（Phase 5），每条发出的消息显示送到哪一步；24 小时规则由后端算。
// 列表每 15 秒、打开的对话每 10 秒自动更新：病人的新消息、送达状态会自己出现。

import { SendIcon } from "lucide-react";
import { useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";
import * as api from "../api";
import { Avatar, Badge, Empty, ErrorBox, Loading, Notice, Tabs, usePageTitle } from "../components";
import { Button } from "../components/ui/button";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { cn } from "../lib/utils";

/** 左右两块的外框：白色、圆角，里面自己上下拉 */
const pane = "min-h-0 overflow-y-auto rounded-xl border bg-card shadow-xs";
import { formatDateTime, formatPhone } from "../format";
import { useAction, useLoad } from "../hooks";
import type { Conversation, ConversationDetail, ConversationMode, Sender, WaStatus } from "../types";

type Filter = "OPEN" | ConversationMode;

const FILTERS: { value: Filter; label: string }[] = [
  { value: "OPEN", label: "Open" },
  { value: "HUMAN", label: "Needs staff" },
  { value: "BOT", label: "AI replying" },
  { value: "CLOSED", label: "Closed" },
];

const MODE_LABEL: Record<ConversationMode, string> = {
  BOT: "AI",
  HUMAN: "Staff",
  CLOSED: "Closed",
};

const SENDER_LABEL: Record<Sender, string> = {
  CUSTOMER: "Patient",
  BOT: "AI",
  STAFF: "Staff",
};

const STATUS_LABEL: Record<WaStatus, string> = {
  ACCEPTED: "Sending…",
  SENT: "Sent",
  DELIVERED: "Delivered",
  READ: "Read",
  FAILED: "Not delivered",
};

const MAX_REPLY_LENGTH = 4096; // WhatsApp 一条文字消息最长 4096 个字（= backend MAX_TEXT_LENGTH）

function displayName(c: Conversation): string {
  return c.profile_name || formatPhone(c.wa_phone);
}

function ConversationList({ selectedId }: { selectedId: number | null }) {
  const [filter, setFilter] = useState<Filter>("OPEN");
  const list = useLoad(() => api.conversations.list(filter === "OPEN" ? undefined : filter), [filter], 15_000);

  return (
    <section className={cn(pane, "flex flex-col", selectedId && "max-[860px]:hidden")}>
      <div className="sticky top-0 z-[1] flex flex-col gap-3 border-b bg-card p-4">
        <h1 className="text-lg font-semibold tracking-tight">Conversations</h1>
        <Tabs label="Conversation filter" value={filter} options={FILTERS} onChange={setFilter} />
      </div>
      <div className="flex flex-col gap-3 p-2 empty:hidden [&>[data-slot=alert]]:m-2">
        <ErrorBox message={list.error} onRetry={list.reload} />
        {list.data === undefined ? (
          list.loading && <div className="p-2"><Loading /></div>
        ) : list.data.length === 0 ? (
          <Empty>No conversations.</Empty>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
            {list.data.map((c) => {
              const selected = c.id === selectedId;
              return (
                <li key={c.id}>
                  <Link
                    to={`/conversations/${c.id}`}
                    aria-current={selected ? "page" : undefined}
                    className={cn(
                      "flex gap-3 rounded-lg p-3 text-foreground no-underline transition-colors outline-none hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/30",
                      selected && "bg-brand-soft hover:bg-brand-soft",
                    )}
                  >
                    <Avatar name={displayName(c)} />
                    <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <div className="flex items-start justify-between gap-2">
                        <strong className="truncate font-semibold">{displayName(c)}</strong>
                        <Badge kind={c.mode}>{MODE_LABEL[c.mode]}</Badge>
                      </div>
                      {c.last_message_preview && (
                        <div className="line-clamp-2 text-sm text-text-2">
                          {c.last_message_sender && (
                            <span className="text-muted-foreground">{SENDER_LABEL[c.last_message_sender]}: </span>
                          )}
                          {c.last_message_preview}
                        </div>
                      )}
                      <div className="text-xs text-muted-foreground">
                        {formatDateTime(c.last_message_at ?? c.created_at)}
                        {c.assigned_staff_name && ` · ${c.assigned_staff_name}`}
                      </div>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}

/** 回复病人。WhatsApp 规定：病人最后一条消息 24 小时之后，只能发预先审批的模板消息（还没有）。 */
function ReplyForm({ conversation: c, onSent }: { conversation: ConversationDetail; onSent: () => void }) {
  const [text, setText] = useState("");
  const action = useAction();

  if (c.mode === "CLOSED") return null;

  const ends = c.reply_window_ends_at;
  if (!ends || new Date(ends).getTime() <= Date.now()) {
    return (
      <Notice tone="neutral">
        {ends
          ? "More than 24 hours since the patient's last message. "
          : "The patient has not sent a message yet. "}
        WhatsApp only allows approved template messages now, which are not available yet.
      </Notice>
    );
  }

  async function send(e?: FormEvent) {
    e?.preventDefault();
    if (!text.trim() || action.busy) return;
    if (await action.run(() => api.conversations.reply(c.id, text))) {
      setText("");
      onSent();
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) void send(); // Ctrl + Enter 送出
  }

  return (
    <form className="flex flex-col gap-2 border-t pt-4" onSubmit={send}>
      <Label className="flex flex-col items-stretch gap-1.5 text-text-2">
        Reply on WhatsApp
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          maxLength={MAX_REPLY_LENGTH}
          rows={3}
          placeholder="Type your reply…"
          className="font-normal"
        />
      </Label>
      <ErrorBox message={action.error} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-xs text-muted-foreground">
          You can reply until {formatDateTime(ends)}.
          {c.mode === "BOT" && " Replying takes over this conversation from the AI."}
        </span>
        <Button type="submit" disabled={action.busy || !text.trim()}>
          <SendIcon />
          {action.busy ? "Sending…" : "Send"}
        </Button>
      </div>
    </form>
  );
}

function ConversationView({ id }: { id: number }) {
  const conversation = useLoad(() => api.conversations.get(id), [id], 10_000);
  const action = useAction();
  const navigate = useNavigate();
  const c = conversation.data;

  async function act(change: (id: number) => Promise<ConversationDetail>) {
    if (await action.run(() => change(id))) conversation.reload();
  }

  if (c === undefined) {
    return (
      <section className={cn(pane, "flex flex-col gap-4 p-5")}>
        <ErrorBox message={conversation.error} onRetry={conversation.reload} />
        {conversation.loading && <Loading />}
      </section>
    );
  }

  return (
    <section className={cn(pane, "flex flex-col gap-4 p-5")}>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b pb-4">
        <div className="flex min-w-0 items-center gap-3">
          <Avatar name={displayName(c)} className="size-10 text-sm" />
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold">{displayName(c)}</h2>
            <div className="text-xs text-muted-foreground">
              {formatPhone(c.wa_phone)} · started {formatDateTime(c.created_at)}
              {c.closed_at && ` · closed ${formatDateTime(c.closed_at)}`}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {c.mode === "BOT" && (
            <Button type="button" disabled={action.busy} onClick={() => act(api.conversations.takeOver)}>
              Take over
            </Button>
          )}
          {c.mode === "HUMAN" && (
            <Button type="button" variant="outline" disabled={action.busy} onClick={() => act(api.conversations.handBack)}>
              Hand back to AI
            </Button>
          )}
          {c.mode !== "CLOSED" && (
            <Button
              type="button"
              variant="outline"
              disabled={action.busy}
              onClick={() => {
                if (window.confirm("Close this conversation? If the patient writes again, a new conversation starts.")) {
                  void act(api.conversations.close);
                }
              }}
            >
              Close
            </Button>
          )}
          <Button type="button" variant="ghost" onClick={() => navigate("/conversations")}>
            Back to list
          </Button>
        </div>
      </header>

      <Notice tone={c.mode === "BOT" ? "info" : c.mode === "HUMAN" ? "warning" : "neutral"}>
        {c.mode === "BOT" && "The AI is replying to this conversation."}
        {c.mode === "HUMAN" &&
          `Staff is handling this conversation${c.assigned_staff_name ? ` (${c.assigned_staff_name})` : ""}. The AI will not reply.`}
        {c.mode === "CLOSED" && "This conversation is closed."}
        {c.handover_reason && <div>Handover reason: {c.handover_reason}</div>}
      </Notice>

      <ErrorBox message={action.error ?? conversation.error} />

      <ol className="m-0 flex flex-1 list-none flex-col gap-3 p-0 py-1" aria-label="Messages">
        {c.messages.map((m) => {
          const patient = m.sender === "CUSTOMER";
          return (
            <li key={m.id} className={cn("flex max-w-[min(75%,640px)] flex-col gap-1", patient ? "self-start" : "items-end self-end")}>
              <div
                className={cn(
                  "rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap [overflow-wrap:anywhere]",
                  patient && "rounded-bl-sm bg-muted",
                  m.sender === "BOT" && "rounded-br-sm bg-bubble-ai",
                  m.sender === "STAFF" && "rounded-br-sm bg-bubble-staff",
                )}
              >
                {m.body}
              </div>
              <div className="text-xs text-muted-foreground">
                {SENDER_LABEL[m.sender]} · {formatDateTime(m.created_at)}
                {m.wa_status && (
                  <span className={cn(m.wa_status === "READ" && "text-info", m.wa_status === "FAILED" && "font-medium text-destructive")}>
                    {" "}· {STATUS_LABEL[m.wa_status]}
                  </span>
                )}
              </div>
              {m.wa_status === "FAILED" && <div className="text-xs text-destructive">{m.wa_error}</div>}
            </li>
          );
        })}
      </ol>

      <ReplyForm conversation={c} onSent={conversation.reload} />
    </section>
  );
}

export default function ConversationsPage() {
  usePageTitle("Conversations");
  const { id } = useParams();
  const selectedId = id !== undefined && /^\d+$/.test(id) ? Number(id) : null;

  return (
    // 电脑萤幕：左边列表、右边对话，各自上下拉。窄的萤幕：打开一段对话时只显示对话，没打开时只显示列表
    <div className="mx-auto grid max-w-[1400px] gap-4 min-[861px]:h-[calc(100vh-76px)] min-[861px]:grid-cols-[340px_minmax(0,1fr)]">
      <ConversationList selectedId={selectedId} />
      {selectedId ? (
        <ConversationView key={selectedId} id={selectedId} />
      ) : (
        <section className={cn(pane, "flex items-center justify-center p-5 max-[860px]:hidden [&>div]:border-0")}>
          <Empty>Select a conversation.</Empty>
        </section>
      )}
    </div>
  );
}
