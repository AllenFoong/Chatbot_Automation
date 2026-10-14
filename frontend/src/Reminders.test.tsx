import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { whatsappLink } from "./pages/RemindersPage";
import { STAFF, err, fakeApi, fakeReminderList, ok } from "./test/fakeApi";
import type { ReminderRecord } from "./types";
import { renderApp } from "./test/render";

const OPENED: ReminderRecord = {
  status: "OPENED",
  updated_at: "2026-10-08T02:05:00Z",
  staff_name: "Amy Tan",
  changed: false,
};

const base = {
  "GET /api/auth/me": ok(STAFF),
  "GET /api/conversations?mode=HUMAN": ok([]),
  "GET /api/requests?status=PENDING": ok([]),
};

// jsdom 不会打开 whatsapp:// 连结：只挡住这种连结的预设动作，画面上的 onClick 照跑
function blockWhatsAppLinks(e: MouseEvent) {
  if ((e.target as Element | null)?.closest?.('a[href^="whatsapp:"]')) e.preventDefault();
}
beforeEach(() => document.addEventListener("click", blockWhatsAppLinks));
afterEach(() => {
  document.removeEventListener("click", blockWhatsAppLinks);
  vi.restoreAllMocks();
});

describe("reminders", () => {
  it("shows the family as one message with Open in WhatsApp", async () => {
    const { calls } = fakeApi({
      ...base,
      "GET /api/reminders": ok(fakeReminderList()),
      "POST /api/reminders/opened": ok(OPENED),
    });
    renderApp("/reminders");
    expect(await screen.findByRole("heading", { name: "Reminders" })).toBeInTheDocument();
    expect(await screen.findByText(/Preview only: this list is read from GPiS_Dev/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Ready 1" })).toHaveAttribute("aria-selected", "true");

    const card = screen.getByText("DEMO PATIENT A & DEMO PATIENT B").closest("li")!;
    expect(within(card).getByText("+60120000001")).toBeInTheDocument();
    const open = within(card).getByRole("link", { name: "Open in WhatsApp" });
    expect(open).toHaveAttribute(
      "href",
      "whatsapp://send?phone=60120000001&text=NAME%3A%20DEMO%20PATIENT%20A%20%26%20DEMO%20PATIENT%20B%0ATIME%3A%2010%3A00%20AM%20%26%2010%3A30%20AM",
    );

    expect(screen.getByText("Opened in WhatsApp: 0 of 1")).toBeInTheDocument();
    await userEvent.setup().click(open);
    expect(await within(card).findByText("Opened")).toBeInTheDocument();
    expect(screen.getByText("Opened in WhatsApp: 1 of 1")).toBeInTheDocument(); // 不用重新读名单就更新
    expect(within(card).getByRole("link", { name: "Open in WhatsApp again" })).toBeInTheDocument();
    expect(within(card).getByText(/Opened in WhatsApp by Amy Tan/)).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")).toEqual({
      method: "POST",
      path: "/api/reminders/opened",
      body: { date: "2026-10-09", phone: "60120000001" },
    });
  });

  it("still shows Opened after going to Needs staff and back", async () => {
    // 以前按过的只记在卡片里：切到 Needs staff 卡片被拿掉，回到 Ready 又显示 To send（重新整理才对）
    const { calls } = fakeApi({
      ...base,
      "GET /api/reminders": ok(fakeReminderList()),
      "POST /api/reminders/opened": ok(OPENED),
    });
    renderApp("/reminders");
    const user = userEvent.setup();
    const card = (await screen.findByText("DEMO PATIENT A & DEMO PATIENT B")).closest("li")!;
    await user.click(within(card).getByRole("link", { name: "Open in WhatsApp" }));
    expect(await within(card).findByText("Opened")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Needs staff/ }));
    expect(screen.queryByText("DEMO PATIENT A & DEMO PATIENT B")).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /Ready/ }));

    const again = screen.getByText("DEMO PATIENT A & DEMO PATIENT B").closest("li")!;
    expect(within(again).getByText("Opened")).toBeInTheDocument();
    expect(within(again).queryByText("To send")).not.toBeInTheDocument();
    expect(within(again).getByRole("link", { name: "Open in WhatsApp again" })).toBeInTheDocument();
    expect(within(again).getByText(/Opened in WhatsApp by Amy Tan/)).toBeInTheDocument();
    expect(screen.getByText("Opened in WhatsApp: 1 of 1")).toBeInTheDocument();
    expect(calls.filter((c) => c.path.startsWith("/api/reminders") && c.method === "GET")).toHaveLength(1); // 没有重新读名单
  });

  it("shows what another staff did and can mark it as not sent", async () => {
    const list = fakeReminderList();
    list.ready = list.ready.map((g) => ({ ...g, record: { ...OPENED, changed: true } }));
    fakeApi({
      ...base,
      "GET /api/reminders": ok(list),
      "POST /api/reminders/not-sent": ok({ ...OPENED, status: "NOT_SENT" }),
    });
    renderApp("/reminders");
    const card = (await screen.findByText("DEMO PATIENT A & DEMO PATIENT B")).closest("li")!;
    expect(within(card).getByText("Opened")).toBeInTheDocument();
    expect(screen.getByText("Opened in WhatsApp: 1 of 1")).toBeInTheDocument();
    expect(within(card).getByText(/GPiS changed after this was opened/)).toBeInTheDocument();

    await userEvent.setup().click(within(card).getByRole("button", { name: "Mark as not sent" }));
    expect(await within(card).findByText("Not sent")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Open in WhatsApp" })).toBeInTheDocument();
    expect(within(card).getByText(/Marked as not sent by Amy Tan/)).toBeInTheDocument();
  });

  it("shows the error when opening cannot be recorded", async () => {
    fakeApi({
      ...base,
      "GET /api/reminders": ok(fakeReminderList()),
      "POST /api/reminders/opened": err(409, "This reminder is not ready any more. Refresh the list."),
    });
    renderApp("/reminders");
    const card = (await screen.findByText("DEMO PATIENT A & DEMO PATIENT B")).closest("li")!;
    await userEvent.setup().click(within(card).getByRole("link", { name: "Open in WhatsApp" }));
    expect(await within(card).findByRole("alert")).toHaveTextContent("not ready any more");
    expect(within(card).queryByText("Opened")).not.toBeInTheDocument();
  });

  it("stops reminders for a number after NO WA and can allow them again", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    let optedOut = false;
    const listNow = () => {
      const list = fakeReminderList();
      if (!optedOut) return list;
      const family = { ...list.ready[0], opted_out: true, whatsapp_allowed: false, problems: ["Opted out of reminders"] };
      return { ...list, ready: [], needs_staff: [family, ...list.needs_staff] };
    };
    const { calls } = fakeApi({
      ...base,
      "GET /api/reminders": () => ok(listNow()),
      "PUT /api/reminders/opt-out": (body) => {
        optedOut = (body as { opted_out: boolean }).opted_out;
        return ok(body);
      },
    });
    renderApp("/reminders");
    const user = userEvent.setup();
    const card = (await screen.findByText("DEMO PATIENT A & DEMO PATIENT B")).closest("li")!;
    await user.click(within(card).getByRole("button", { name: "NO WA: stop reminders" }));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("Stop reminders for +60120000001?"));
    expect(await screen.findByRole("tab", { name: "Ready 0" })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Needs staff 2" }));
    expect(screen.getByText("Opted out of reminders")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Allow reminders again" }));
    expect(await screen.findByRole("tab", { name: "Ready 1" })).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "PUT").map((c) => c.body)).toEqual([
      { phone: "60120000001", opted_out: true },
      { phone: "60120000001", opted_out: false },
    ]);
  });

  it("hides Open in WhatsApp when the server does not allow it", async () => {
    const list = fakeReminderList();
    list.ready = list.ready.map((g) => ({ ...g, whatsapp_allowed: false }));
    fakeApi({ ...base, "GET /api/reminders": ok(list) });
    renderApp("/reminders");
    expect(await screen.findByText("Open in WhatsApp is off for this list.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Open in WhatsApp/ })).not.toBeInTheDocument();
  });

  it("lists what needs staff and what is not an appointment", async () => {
    fakeApi({ ...base, "GET /api/reminders": ok(fakeReminderList()) });
    renderApp("/reminders");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "Needs staff 1" }));
    expect(screen.getByText("DEMO PATIENT C", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("Singapore")).toBeInTheDocument();
    expect(screen.getAllByText("Lab work not marked as arrived (*C)")).toHaveLength(1);
    expect(screen.queryByRole("link", { name: /Open in WhatsApp/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Not appointments 3" }));
    expect(screen.getByText(/Cancelled or postponed/)).toHaveTextContent("Cancelled or postponed: 2");
  });

  it("can show another date and go back", async () => {
    const { calls } = fakeApi({
      ...base,
      "GET /api/reminders": ok(fakeReminderList()),
      "GET /api/reminders?date=2026-09-02": ok(
        fakeReminderList({ dates: ["2026-09-02"], ready: [], needs_staff: [], not_appointments: [] }),
      ),
    });
    renderApp("/reminders");
    const user = userEvent.setup();
    fireEvent.change(await screen.findByLabelText("Appointment date"), { target: { value: "2026-09-02" } });
    await user.click(screen.getByRole("button", { name: "Show" }));
    expect(await screen.findByText("No reminders to send.")).toBeInTheDocument();
    expect(screen.getByText(/Appointments on Wed 02 Sep 2026/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to today's reminders" }));
    expect(await screen.findByText("DEMO PATIENT A & DEMO PATIENT B")).toBeInTheDocument();
    expect(calls.filter((c) => c.path.startsWith("/api/reminders")).map((c) => c.path)).toEqual([
      "/api/reminders",
      "/api/reminders?date=2026-09-02",
      "/api/reminders",
    ]);
  });

  it("shows the server's error", async () => {
    fakeApi({ ...base, "GET /api/reminders": err(503, "Cannot read GPiS. See the server log.") });
    renderApp("/reminders");
    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot read GPiS");
  });

  it("builds the WhatsApp link with the message encoded", () => {
    expect(whatsappLink("60120000001", "温馨提醒💕\nA & B")).toBe(
      "whatsapp://send?phone=60120000001&text=%E6%B8%A9%E9%A6%A8%E6%8F%90%E9%86%92%F0%9F%92%95%0AA%20%26%20B",
    );
  });
});
