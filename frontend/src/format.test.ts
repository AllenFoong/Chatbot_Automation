import { describe, expect, it } from "vitest";
import { clinicToday, formatDate, formatDateTime, formatPhone, formatTime, HALF_HOURS } from "./format";

describe("format", () => {
  it("shows time points in Malaysia time (UTC+8)", () => {
    expect(formatDateTime("2026-10-06T01:47:00Z")).toBe("06 Oct 2026, 09:47");
    expect(formatDateTime("2026-10-06T17:30:00+00:00")).toBe("07 Oct 2026, 01:30");
  });

  it("shows dates without moving them to another day", () => {
    expect(formatDate("2026-10-09")).toBe("Fri 09 Oct 2026");
    expect(formatDate("2026-02-16")).toBe("Mon 16 Feb 2026");
  });

  it("uses the clinic's date, not the computer's", () => {
    expect(clinicToday(new Date("2026-10-06T16:30:00Z"))).toBe("2026-10-07");
    expect(clinicToday(new Date("2026-10-06T15:59:00Z"))).toBe("2026-10-06");
  });

  it("formats times and phones", () => {
    expect(formatTime("16:00:00")).toBe("16:00");
    expect(formatPhone("60120000001")).toBe("+60120000001");
  });

  it("offers every half hour", () => {
    expect(HALF_HOURS).toHaveLength(48);
    expect(HALF_HOURS.slice(17, 20)).toEqual(["08:30", "09:00", "09:30"]);
  });
});
