// 日期、时间的显示方式。
// - 时间点（created_at 等）后端存的是绝对时间（timestamptz），一律转成诊所的时区显示，
//   这样不管电脑的时区设成什么，员工看到的都是马来西亚时间。
// - 日期（2026-10-09）、时段（16:00:00）本来就没有时区，照原样显示，不能用 new Date() 转（会差一天）。

export const CLINIC_TIME_ZONE = "Asia/Kuala_Lumpur";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;

/** 1 = Monday … 7 = Sunday（和 doctor_schedules.weekday 一样） */
export function weekdayName(weekday: number): string {
  return WEEKDAYS[weekday - 1] ?? "?";
}

const dateTimeFormat = new Intl.DateTimeFormat("en-GB", {
  timeZone: CLINIC_TIME_ZONE,
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** "2026-10-06T06:05:00+00:00" → "06 Oct 2026, 14:05"（马来西亚时间） */
export function formatDateTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : dateTimeFormat.format(d);
}

/** "2026-10-09" → "Fri 09 Oct 2026" */
export function formatDate(isoDate: string | null): string {
  if (!isoDate) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!m) return isoDate;
  const [year, month, day] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const weekday = (new Date(Date.UTC(year, month - 1, day)).getUTCDay() + 6) % 7; // 0 = Monday
  return `${WEEKDAYS[weekday]} ${m[3]} ${MONTHS[month - 1]} ${year}`;
}

/** "16:00:00" → "16:00" */
export function formatTime(time: string | null): string {
  return time ? time.slice(0, 5) : "";
}

/** 诊所今天的日期 "2026-10-06"（马来西亚时间） */
export function clinicToday(now: Date = new Date()): string {
  // en-CA 的日期格式刚好是 YYYY-MM-DD
  return new Intl.DateTimeFormat("en-CA", { timeZone: CLINIC_TIME_ZONE }).format(now);
}

/** 60120000001 → +60120000001（wa_phone 存的是国际格式、只有数字） */
export function formatPhone(phone: string | null): string {
  return phone ? `+${phone}` : "";
}

/** 排班用的时段：每 30 分钟一格（数据库规定时间要在 30 分钟格上）。 */
export const HALF_HOURS: string[] = Array.from({ length: 48 }, (_, i) => {
  const h = String(Math.floor(i / 2)).padStart(2, "0");
  return `${h}:${i % 2 ? "30" : "00"}`;
});

/** 打开 WhatsApp Desktop 的对话，消息已经填好（D54）。
 *  用 whatsapp:// 而不是 wa.me 网址：网址会留在浏览器的历史记录（有号码和名字，D31）。 */
export function whatsappLink(phone: string, message: string): string {
  return `whatsapp://send?phone=${phone}&text=${encodeURIComponent(message)}`;
}
