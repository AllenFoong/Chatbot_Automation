import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { whatsappLink } from "./pages/RemindersPage";
import { STAFF, err, fakeApi, fakeReminderList, ok } from "./test/fakeApi";
import { renderApp } from "./test/render";

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
afterEach(() => document.removeEventListener("click", blockWhatsAppLinks));

describe("reminders", () => {
  it("shows the family as one message with Open in WhatsApp", async () => {
    fakeApi({ ...base, "GET /api/reminders": ok(fakeReminderList()) });
    renderApp("/reminders");
    expect(await screen.findByRole("heading", { name: "Reminders" })).toBeInTheDocument();
    expect(await screen.findByText(/Preview only: this list is read from GPiS_Dev/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Ready (1)" })).toHaveAttribute("aria-selected", "true");

    const card = screen.getByText("DEMO PATIENT A & DEMO PATIENT B").closest("li")!;
    expect(within(card).getByText("+60120000001")).toBeInTheDocument();
    const open = within(card).getByRole("link", { name: "Open in WhatsApp" });
    expect(open).toHaveAttribute(
      "href",
      "whatsapp://send?phone=60120000001&text=NAME%3A%20DEMO%20PATIENT%20A%20%26%20DEMO%20PATIENT%20B%0ATIME%3A%2010%3A00%20AM%20%26%2010%3A30%20AM",
    );

    await userEvent.setup().click(open);
    expect(within(card).getByText("Opened")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Open in WhatsApp again" })).toBeInTheDocument();
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
    await user.click(await screen.findByRole("tab", { name: "Needs staff (1)" }));
    expect(screen.getByText("DEMO PATIENT C", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("Singapore")).toBeInTheDocument();
    expect(screen.getAllByText("Lab work not marked as arrived (*C)")).toHaveLength(1);
    expect(screen.queryByRole("link", { name: /Open in WhatsApp/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Not appointments (3)" }));
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
