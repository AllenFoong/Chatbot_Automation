// 测试用的假后端：把 fetch 换掉，按 "方法 网址" 回传假资料。全部是假名字、假号码。

import { vi } from "vitest";
import type { AppointmentRequest, Conversation, ConversationDetail, StaffMember } from "../types";

type Reply = { status: number; body?: unknown };
type Handler = (body: unknown) => Reply;
export type Routes = Record<string, Reply | Handler>;

export interface Call {
  method: string;
  path: string;
  body: unknown;
}

/** routes 的 key 例："GET /api/auth/me"、"POST /api/requests/1/confirm"（网址含 query string） */
export function fakeApi(routes: Routes) {
  const calls: Call[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const path = String(input);
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    calls.push({ method, path, body });
    const route = routes[`${method} ${path}`];
    if (!route) return new Response(JSON.stringify({ detail: `No fake route for ${method} ${path}` }), { status: 404 });
    const reply = typeof route === "function" ? route(body) : route;
    if (reply.status === 204) return new Response(null, { status: 204 });
    return new Response(JSON.stringify(reply.body ?? null), {
      status: reply.status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export const ok = (body?: unknown): Reply => ({ status: 200, body });
export const err = (status: number, detail: unknown): Reply => ({ status, body: { detail } });

export const ADMIN: StaffMember = { id: 1, username: "boss", name: "Demo Boss", role: "ADMIN", active: true };
export const STAFF: StaffMember = { id: 2, username: "amy", name: "Demo Amy", role: "STAFF", active: true };

export function fakeRequest(overrides: Partial<AppointmentRequest> = {}): AppointmentRequest {
  return {
    id: 1,
    status: "PENDING",
    customer_id: 10,
    customer_name: "Demo Kid A",
    customer_phone: "60120000001",
    gpis_contact_id: null,
    conversation_id: 5,
    service_code: "S+P",
    service_name: "Scaling & polishing",
    doctor_id: "PHANG",
    preferred_date: "2026-10-09",
    preferred_slot: "16:00:00",
    duration_minutes: 30,
    notes: null,
    group_id: null,
    gpis_appointment_id: null,
    handled_by: null,
    handled_at: null,
    created_at: "2026-10-06T01:47:00Z",
    ...overrides,
  };
}

export function fakeConversation(overrides: Partial<ConversationDetail> = {}): ConversationDetail {
  const base: Conversation = {
    id: 5,
    wa_phone: "60120000001",
    profile_name: "Demo Mum",
    mode: "BOT",
    assigned_staff_id: null,
    assigned_staff_name: null,
    handover_reason: null,
    created_at: "2026-10-06T01:47:00Z",
    closed_at: null,
    last_message_at: "2026-10-06T01:48:00Z",
    last_message_sender: "BOT",
    last_message_preview: "Noted. Our staff will confirm shortly.",
  };
  return {
    ...base,
    messages: [
      { id: 1, sender: "CUSTOMER", staff_id: null, body: "Hi, can I book scaling?", wa_status: null, wa_error: null, created_at: "2026-10-06T01:47:00Z" },
      { id: 2, sender: "BOT", staff_id: null, body: "Noted. Our staff will confirm shortly.", wa_status: null, wa_error: null, created_at: "2026-10-06T01:48:00Z" },
    ],
    // 24 小时规则：默认还能回复（20 小时后才截止）
    reply_window_ends_at: new Date(Date.now() + 20 * 3600_000).toISOString(),
    ...overrides,
  };
}
