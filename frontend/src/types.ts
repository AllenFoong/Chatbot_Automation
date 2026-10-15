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
  // D70: SYSTEM = found in GPiS by the system; CONFIRMED with no patient_notified_at = staff must tell the patient
  confirmed_by: DoneBy | null;
  patient_notified_at: string | null;
  patient_notified_by: DoneBy | null;
  notify_problem: string | null;
}

export type DoneBy = "SYSTEM" | "STAFF";

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

// ---------- 预约提醒（app/api/reminders.py，Phase 5b） ----------

export type PhoneKind = "MY_MOBILE" | "SG_MOBILE" | "OTHER_COUNTRY" | "LANDLINE" | "MISSING";

export interface ReminderLine {
  appointment_ids: number[];
  time: string | null; // "10:00"
  doctor_id: string;
  doctor_name: string;
  patient_name: string;
  status: string | null;
  problems: string[];
}

export type ReminderStatus = "OPENED" | "NOT_SENT";

/** 员工对这条提醒做过什么（后端的 reminders 表） */
export interface ReminderRecord {
  status: ReminderStatus;
  updated_at: string;
  staff_name: string | null;
  /** 按过之后 GPiS 多了 / 少了预约：要再看一次 */
  changed: boolean;
}

/** 发给一个号码的一条提醒（同一天）。没有号码的病人各自一组。 */
export interface ReminderGroup {
  key: string;
  date: string;
  phone: string | null;
  phone_kind: PhoneKind;
  lines: ReminderLine[];
  problems: string[];
  message: string | null;
  /** 能不能显示 Open in WhatsApp（D54：只有读主机的 GPiS，或允许名单里的号码） */
  whatsapp_allowed: boolean;
  /** 这个号码不要提醒（签名表写 NO WA，D55） */
  opted_out: boolean;
  record: ReminderRecord | null;
}

export interface ReminderList {
  dates: string[];
  suggested_dates: string[];
  source: string;
  production: boolean;
  read_at: string;
  ready: ReminderGroup[];
  needs_staff: ReminderGroup[];
  not_appointments: { reason: string; count: number }[];
}
