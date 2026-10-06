import { describe, expect, it } from "vitest";
import { scheduleProblems } from "./schedule";
import type { ScheduleDay } from "./types";

const day = (overrides: Partial<ScheduleDay>): ScheduleDay => ({
  weekday: 6,
  is_working: true,
  start_time: "09:00:00",
  last_slot: "15:30:00",
  break_start: null,
  break_end: null,
  ...overrides,
});

describe("scheduleProblems", () => {
  it("accepts a normal day and a day off", () => {
    expect(scheduleProblems([day({ break_start: "13:00", break_end: "14:00:00" }), day({ weekday: 7, is_working: false, start_time: null, last_slot: null })])).toEqual([]);
  });

  it("needs start and last slot on a working day", () => {
    expect(scheduleProblems([day({ last_slot: null })])).toEqual(["Sat: choose the start time and the last slot."]);
  });

  it("rejects a last slot before the start", () => {
    expect(scheduleProblems([day({ last_slot: "08:30" })])).toEqual([
      "Sat: the last slot (08:30) cannot be before the start (09:00).",
    ]);
  });

  it("needs both break times, in order", () => {
    expect(scheduleProblems([day({ break_start: "12:00" })])).toEqual([
      "Sat: choose both break start and break end, or neither.",
    ]);
    expect(scheduleProblems([day({ break_start: "13:00", break_end: "12:00" })])).toEqual([
      "Sat: the break must end after it starts.",
    ]);
  });
});
