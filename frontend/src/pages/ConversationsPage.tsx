// 对话：左边列表，右边打开的那一段（网址 /conversations/12）。
// 员工可以接手（AI 停止回复）、交回 AI、结束对话（docs/architecture.md 第 5 节）。
// 回复病人要等 Phase 5 接上 WhatsApp（D28），这里先不做输入框。
// 列表每 15 秒、打开的对话每 10 秒自动更新（Phase 5 之后病人的消息会自己进来）。

import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import * as api from "../api";
import { Badge, Empty, ErrorBox, Loading, Tabs } from "../components";
import { formatDateTime, formatPhone } from "../format";
import { useAction, useLoad } from "../hooks";
import type { Conversation, ConversationDetail, ConversationMode, Sender } from "../types";

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

function displayName(c: Conversation): string {
  return c.profile_name || formatPhone(c.wa_phone);
}

function ConversationList({ selectedId }: { selectedId: number | null }) {
  const [filter, setFilter] = useState<Filter>("OPEN");
  const list = useLoad(() => api.conversations.list(filter === "OPEN" ? undefined : filter), [filter], 15_000);

  return (
    <section className="list-pane">
      <Tabs label="Conversation filter" value={filter} options={FILTERS} onChange={setFilter} />
      <ErrorBox message={list.error} onRetry={list.reload} />
      {list.data === undefined ? (
        list.loading && <Loading />
      ) : list.data.length === 0 ? (
        <Empty>No conversations.</Empty>
      ) : (
        <ul className="conversation-list">
          {list.data.map((c) => (
            <li key={c.id}>
              <Link
                to={`/conversations/${c.id}`}
                className={c.id === selectedId ? "selected" : undefined}
                aria-current={c.id === selectedId ? "page" : undefined}
              >
                <div className="row-between">
                  <strong>{displayName(c)}</strong>
                  <Badge kind={c.mode}>{MODE_LABEL[c.mode]}</Badge>
                </div>
                {c.last_message_preview && (
                  <div className="preview">
                    {c.last_message_sender && <span className="muted">{SENDER_LABEL[c.last_message_sender]}: </span>}
                    {c.last_message_preview}
                  </div>
                )}
                <div className="muted small">
                  {formatDateTime(c.last_message_at ?? c.created_at)}
                  {c.assigned_staff_name && ` · ${c.assigned_staff_name}`}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
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
      <section className="detail-pane">
        <ErrorBox message={conversation.error} onRetry={conversation.reload} />
        {conversation.loading && <Loading />}
      </section>
    );
  }

  return (
    <section className="detail-pane">
      <header className="detail-header">
        <div>
          <h2>{displayName(c)}</h2>
          <div className="muted">
            {formatPhone(c.wa_phone)} · started {formatDateTime(c.created_at)}
            {c.closed_at && ` · closed ${formatDateTime(c.closed_at)}`}
          </div>
        </div>
        <div className="actions">
          {c.mode === "BOT" && (
            <button type="button" className="primary" disabled={action.busy} onClick={() => act(api.conversations.takeOver)}>
              Take over
            </button>
          )}
          {c.mode === "HUMAN" && (
            <button type="button" disabled={action.busy} onClick={() => act(api.conversations.handBack)}>
              Hand back to AI
            </button>
          )}
          {c.mode !== "CLOSED" && (
            <button
              type="button"
              disabled={action.busy}
              onClick={() => {
                if (window.confirm("Close this conversation? If the patient writes again, a new conversation starts.")) {
                  void act(api.conversations.close);
                }
              }}
            >
              Close
            </button>
          )}
          <button type="button" className="link" onClick={() => navigate("/conversations")}>
            Back to list
          </button>
        </div>
      </header>

      <div className={`mode-banner mode-${c.mode.toLowerCase()}`}>
        {c.mode === "BOT" && "The AI is replying to this conversation."}
        {c.mode === "HUMAN" &&
          `Staff is handling this conversation${c.assigned_staff_name ? ` (${c.assigned_staff_name})` : ""}. The AI will not reply.`}
        {c.mode === "CLOSED" && "This conversation is closed."}
        {c.handover_reason && <div>Handover reason: {c.handover_reason}</div>}
      </div>

      <ErrorBox message={action.error ?? conversation.error} />

      <ol className="messages" aria-label="Messages">
        {c.messages.map((m) => (
          <li key={m.id} className={`message from-${m.sender.toLowerCase()}`}>
            <div className="bubble">{m.body}</div>
            <div className="muted small">
              {SENDER_LABEL[m.sender]} · {formatDateTime(m.created_at)}
            </div>
          </li>
        ))}
      </ol>

      <p className="muted small note">
        Replying from this page will be available after WhatsApp is connected (Phase 5). Until then, reply on the
        clinic phone.
      </p>
    </section>
  );
}

export default function ConversationsPage() {
  const { id } = useParams();
  const selectedId = id !== undefined && /^\d+$/.test(id) ? Number(id) : null;

  return (
    <div className={selectedId ? "split has-detail" : "split"}>
      <ConversationList selectedId={selectedId} />
      {selectedId ? (
        <ConversationView key={selectedId} id={selectedId} />
      ) : (
        <section className="detail-pane placeholder">
          <Empty>Select a conversation.</Empty>
        </section>
      )}
    </div>
  );
}
