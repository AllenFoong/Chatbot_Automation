// 排班送出之前先检查，用员工看得懂的话说哪里错。
// 规则和数据库的 CHECK 一样（backend/app/db/models.py 的 DoctorSchedule）：
// 数据库还是最后一道防线，这里只是让错误信息好懂一点。

import { formatTime, weekdayName } from "./format";
import type { ScheduleDay } from "./types";

/** "09:00" 和 "09:00:00" 都转成 "09:00" 再比（字串比大小刚好等于时间先后） */
const hm = (t: string | null) => (t ? formatTime(t) : null);

export function scheduleProblems(days: ScheduleDay[]): string[] {
  const problems: string[] = [];
  for (const d of days) {
    if (!d.is_working) continue;
    const day = weekdayName(d.weekday);
    const [start, last, breakStart, breakEnd] = [hm(d.start_time), hm(d.last_slot), hm(d.break_start), hm(d.break_end)];
    if (!start || !last) {
      problems.push(`${day}: choose the start time and the last slot.`);
    } else if (start > last) {
      problems.push(`${day}: the last slot (${last}) cannot be before the start (${start}).`);
    }
    if ((breakStart === null) !== (breakEnd === null)) {
      problems.push(`${day}: choose both break start and break end, or neither.`);
    } else if (breakStart && breakEnd && breakStart >= breakEnd) {
      problems.push(`${day}: the break must end after it starts.`);
    }
  }
  return problems;
}
