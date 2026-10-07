// API 回传的资料长什么样子：和 backend/app/api/ 里的 Pydantic model 一一对应。
// 后端改了栏位，这里也要改；TypeScript 会指出画面上哪里用到了旧的栏位。
// 日期：date = "2026-10-09"；时间：time = "16:00:00"；时间点：datetime = ISO 8601（有时区）。

export type Role = "ADMIN" | "STAFF";
export type ConversationMode = "BOT" | "HUMAN" | "CLOSED";
export type Sender = "CUSTOMER" | "BOT" | "STAFF";
export type RequestStatus = "PENDING" | "CONFIRMED" | "REJECTED" | "CANCELLED";
/** 发出的消息送到哪一步（Phase 5）：ACCEPTED = WhatsApp 收下了，还没送出 */
export type WaStatus = "ACCEPTED" | "SENT" | "DELIVERED" | "READ" | "FAILED";

// ---------- 登录、员工（app/api/auth.py、staff.py） ----------

export interface StaffMember {
  id: number;
  username: string;
  name: string;
  role: Role;
  active: boolean;
}

export interface StaffIn {
  username: string;
  name: string;
  role: Role;
  password: string;
}

export interface StaffPatch {
  name?: string;
  role?: Role;
  active?: boolean;
  password?: string;
}

// ---------- 对话（app/api/conversations.py） ----------

export interface Message {
  id: number;
  sender: Sender;
  staff_id: number | null;
  body: string;
  wa_status: WaStatus | null;
  wa_error: string | null;
  created_at: string;
}

export interface Conversation {
  id: number;
  wa_phone: string;
  profile_name: string | null;
  mode: ConversationMode;
  assigned_staff_id: number | null;
  assigned_staff_name: string | null;
  handover_reason: string | null;
  created_at: string;
  closed_at: string | null;
  last_message_at: string | null;
  last_message_sender: Sender | null;
  last_message_preview: string | null;
}

export interface ConversationDetail extends Conversation {
  /** WhatsApp 24 小时规则：这个时间之前才能回复（病人最后一条消息 + 24 小时）；病人没发过消息 = null */
  reply_window_ends_at: string | null;
  messages: Message[];
}

// ---------- 预约请求（app/api/requests.py） ----------

export interface AppointmentRequest {
  id: number;
  status: RequestStatus;
  customer_id: number;
  customer_name: string;
  customer_phone: string | null;
  gpis_contact_id: number | null;
  conversation_id: number | null;
  service_code: string;
  service_name: string;
  doctor_id: string | null;
  preferred_date: string | null;
  preferred_slot: string | null;
  duration_minutes: number;
  notes: string | null;
  group_id: string | null;
  gpis_appointment_id: number | null;
  handled_by: number | null;
  handled_at: string | null;
  created_at: string;
}

// ---------- 设置（app/api/settings.py） ----------

export interface Doctor {
  id: string;
  display_name: string;
  remark_tag: string | null;
  active: boolean;
}

export interface ScheduleDay {
  weekday: number; // 1 = Monday … 7 = Sunday
  is_working: boolean;
  start_time: string | null;
  last_slot: string | null;
  break_start: string | null;
  break_end: string | null;
}

export interface Service {
  code: string;
  name: string;
  can_be_third: boolean;
  may_need_1h: boolean;
  ai_can_book: boolean;
  treatment_group: string | null;
  active: boolean;
}

export type ServiceIn = Omit<Service, "active">;

export interface Closure {
  closure_date: string;
  reason: string;
}

export interface HolidayImport {
  added: Closure[];
  already_there: number;
}

export interface Leave {
  doctor_id: string;
  leave_date: string;
  reason: string | null;
}

export interface ClinicSettings {
  max_per_slot: number;
  max_per_slot_for_ai: number;
  clinic_contact_id: number;
}
