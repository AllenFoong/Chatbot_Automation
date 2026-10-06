// 调用后端 /api 的地方都在这里：画面不直接用 fetch。
// - 登录用的是 HttpOnly cookie：JavaScript 读不到也不用管它，浏览器会自动带上（同一个网址）。
// - 后端回错误时，变成 ApiError，画面显示 message。
// - 登录过期（401）时，通知 AuthProvider 回到登录画面。

import type {
  AppointmentRequest,
  ClinicSettings,
  Closure,
  Conversation,
  ConversationDetail,
  ConversationMode,
  Doctor,
  HolidayImport,
  Leave,
  RequestStatus,
  ScheduleDay,
  Service,
  ServiceIn,
  StaffIn,
  StaffMember,
  StaffPatch,
} from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

let onUnauthorized: (() => void) | null = null;

/** 任何"改资料"的请求成功后发出这个事件（例如选单上的数字马上更新）。 */
export const DATA_CHANGED = "api:data-changed";

/** AuthProvider 登记：任何请求回 401（登录过期、被停用）就叫这个函数。 */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

/** 后端的错误有三种样子，都变成一句英文：
 *  {"detail": "Wrong username or password"}
 *  {"detail": "Rejected by a database rule", "rule": "ck_..."}       （数据库约束，main.py）
 *  {"detail": [{"loc": [...], "msg": "..."}]}                          （FastAPI 检查输入，422） */
export function errorMessage(status: number, body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const { detail, rule } = body as { detail: unknown; rule?: unknown };
    if (typeof detail === "string") {
      return typeof rule === "string" ? `${detail} (${rule})` : detail;
    }
    if (Array.isArray(detail)) {
      return detail
        .map((d: { loc?: unknown[]; msg?: string }) => {
          const field = Array.isArray(d.loc) ? d.loc.filter((x) => x !== "body").join(".") : "";
          return field ? `${field}: ${d.msg}` : String(d.msg);
        })
        .join("; ");
    }
  }
  if (status >= 500) return "The server is not responding. Is the backend (uvicorn) running?";
  return `Request failed (HTTP ${status})`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check the network or whether the backend is running.");
  }

  // 登录、登出不算"改资料"
  const changed = method !== "GET" && !path.startsWith("/auth/");

  if (response.status === 204) {
    if (changed) window.dispatchEvent(new Event(DATA_CHANGED));
    return undefined as T;
  }

  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    // 不是 JSON（例如 Vite 连不上 FastAPI 时回的错误页面）
  }

  if (!response.ok) {
    // 登录失败本身也是 401，那时不需要"回到登录画面"
    if (response.status === 401 && path !== "/auth/login") onUnauthorized?.();
    throw new ApiError(response.status, errorMessage(response.status, data));
  }
  if (changed) window.dispatchEvent(new Event(DATA_CHANGED));
  return data as T;
}

/** 重复的资料（409）换成员工看得懂的一句话，例如 "This date is already in the list." */
export async function explainDuplicate<T>(promise: Promise<T>, message: string): Promise<T> {
  try {
    return await promise;
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) throw new ApiError(409, message);
    throw e;
  }
}

/** 网址里的一段：疗程代码有 / 和 +（例 C/UP、S+P），要编码。 */
const seg = (value: string | number) => encodeURIComponent(String(value));

function query(params: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") q.set(key, String(value));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

// ---------- 登录 ----------

export const auth = {
  login: (username: string, password: string) =>
    request<StaffMember>("POST", "/auth/login", { username, password }),
  logout: () => request<void>("POST", "/auth/logout"),
  me: () => request<StaffMember>("GET", "/auth/me"),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("POST", "/auth/password", { current_password, new_password }),
};

// ---------- 对话 ----------

export const conversations = {
  list: (mode?: ConversationMode) => request<Conversation[]>("GET", `/conversations${query({ mode })}`),
  get: (id: number) => request<ConversationDetail>("GET", `/conversations/${seg(id)}`),
  takeOver: (id: number) => request<ConversationDetail>("POST", `/conversations/${seg(id)}/take-over`),
  handBack: (id: number) => request<ConversationDetail>("POST", `/conversations/${seg(id)}/hand-back`),
  close: (id: number) => request<ConversationDetail>("POST", `/conversations/${seg(id)}/close`),
  /** 经 WhatsApp 发给病人；在 AI 回复的对话里回复 = 接手 */
  reply: (id: number, body: string) =>
    request<ConversationDetail>("POST", `/conversations/${seg(id)}/reply`, { body }),
};

// ---------- 预约请求 ----------

export const requests = {
  list: (status: RequestStatus) => request<AppointmentRequest[]>("GET", `/requests${query({ status })}`),
  confirm: (id: number, gpisAppointmentId: number | null) =>
    request<AppointmentRequest>("POST", `/requests/${seg(id)}/confirm`, {
      gpis_appointment_id: gpisAppointmentId,
    }),
  reject: (id: number) => request<AppointmentRequest>("POST", `/requests/${seg(id)}/reject`),
  cancel: (id: number) => request<AppointmentRequest>("POST", `/requests/${seg(id)}/cancel`),
};

// ---------- 设置（看：所有员工；改：只有 ADMIN，后端会检查） ----------

export const settings = {
  doctors: () => request<Doctor[]>("GET", "/doctors"),
  addDoctor: (body: { id: string; display_name: string; remark_tag: string | null }) =>
    request<Doctor>("POST", "/doctors", body),
  updateDoctor: (id: string, body: Partial<Omit<Doctor, "id">>) =>
    request<Doctor>("PATCH", `/doctors/${seg(id)}`, body),
  schedule: (doctorId: string) => request<ScheduleDay[]>("GET", `/doctors/${seg(doctorId)}/schedule`),
  setSchedule: (doctorId: string, days: ScheduleDay[]) =>
    request<ScheduleDay[]>("PUT", `/doctors/${seg(doctorId)}/schedule`, days),

  services: () => request<Service[]>("GET", "/services"),
  addService: (body: ServiceIn) => request<Service>("POST", "/services", body),
  updateService: (code: string, body: Partial<Omit<Service, "code">>) =>
    request<Service>("PATCH", `/services/${seg(code)}`, body),

  closures: (year: number) => request<Closure[]>("GET", `/closures${query({ year })}`),
  addClosure: (body: Closure) => request<Closure>("POST", "/closures", body),
  deleteClosure: (date: string) => request<void>("DELETE", `/closures/${seg(date)}`),
  importHolidays: (year: number) => request<HolidayImport>("POST", "/closures/import-holidays", { year }),

  leaves: (fromDate?: string) => request<Leave[]>("GET", `/leaves${query({ from_date: fromDate })}`),
  addLeave: (body: Leave) => request<Leave>("POST", "/leaves", body),
  deleteLeave: (doctorId: string, date: string) =>
    request<void>("DELETE", `/leaves/${seg(doctorId)}/${seg(date)}`),

  clinic: () => request<ClinicSettings>("GET", "/settings"),
  updateClinic: (body: Partial<ClinicSettings>) => request<ClinicSettings>("PATCH", "/settings", body),
};

// ---------- 员工账号（只有 ADMIN） ----------

export const staff = {
  list: () => request<StaffMember[]>("GET", "/staff"),
  add: (body: StaffIn) => request<StaffMember>("POST", "/staff", body),
  update: (id: number, body: StaffPatch) => request<StaffMember>("PATCH", `/staff/${seg(id)}`, body),
};
