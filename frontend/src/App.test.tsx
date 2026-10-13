import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ADMIN, STAFF, err, fakeApi, fakeConversation, fakeRequest, ok } from "./test/fakeApi";
import { renderApp } from "./test/render";

// 选单上的数字（每个画面都会读）
const counts = {
  "GET /api/conversations?mode=HUMAN": ok([]),
  "GET /api/requests?status=PENDING": ok([]),
};

describe("login", () => {
  it("shows the login form when not logged in, and the error for a wrong password", async () => {
    const { calls } = fakeApi({
      "GET /api/auth/me": err(401, "Please log in"),
      "POST /api/auth/login": err(401, "Wrong username or password"),
    });
    renderApp("/requests");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Username"), "boss");
    await user.type(screen.getByLabelText("Password"), "wrong-pass");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong username or password");
    expect(screen.getByLabelText("Password")).toHaveValue(""); // 密码不留在画面上
    expect(calls.at(-1)?.body).toEqual({ username: "boss", password: "wrong-pass" });
  });

  it("opens the page after logging in", async () => {
    fakeApi({
      "GET /api/auth/me": err(401, "Please log in"),
      "POST /api/auth/login": ok(ADMIN),
      ...counts,
    });
    renderApp("/requests");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Username"), "boss");
    await user.type(screen.getByLabelText("Password"), "demo-pass-1");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("heading", { name: "Appointment requests" })).toBeInTheDocument();
    expect(screen.getByText("Demo Boss")).toBeInTheDocument();
  });

  it("goes back to the login form when the session expires", async () => {
    let expired = false;
    fakeApi({
      "GET /api/auth/me": ok(ADMIN),
      "GET /api/conversations?mode=HUMAN": () => (expired ? err(401, "Please log in") : ok([])),
      "GET /api/requests?status=PENDING": () => (expired ? err(401, "Please log in") : ok([])),
      "GET /api/conversations": ok([]),
    });
    renderApp("/requests");
    await screen.findByRole("heading", { name: "Appointment requests" });
    expired = true;
    await userEvent.setup().click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByRole("button", { name: "Log in" })).toBeInTheDocument();
  });
});

describe("roles", () => {
  it("STAFF does not see staff accounts or edit buttons", async () => {
    fakeApi({
      "GET /api/auth/me": ok(STAFF),
      ...counts,
      "GET /api/services": ok([
        { code: "S+P", name: "Scaling & polishing", can_be_third: true, may_need_1h: false, ai_can_book: true, treatment_group: null, active: true },
      ]),
    });
    renderApp("/settings/services");
    expect(await screen.findByText("Scaling & polishing")).toBeInTheDocument();
    expect(screen.getByText(/Only an admin can change them/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Staff accounts" })).not.toBeInTheDocument();
  });

  it("ADMIN sees staff accounts and can edit", async () => {
    fakeApi({
      "GET /api/auth/me": ok(ADMIN),
      ...counts,
      "GET /api/services": ok([
        { code: "S+P", name: "Scaling & polishing", can_be_third: true, may_need_1h: false, ai_can_book: true, treatment_group: null, active: true },
      ]),
    });
    renderApp("/settings/services");
    expect(await screen.findByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Staff accounts" })).toBeInTheDocument();
  });
});

describe("treatments", () => {
  const service = (code: string, treatment_group: string | null) => ({
    code, name: code, can_be_third: false, may_need_1h: false, ai_can_book: false, treatment_group, active: true,
  });

  it("keeps the treatment group when editing, even one the page does not know", async () => {
    const { calls } = fakeApi({
      "GET /api/auth/me": ok(ADMIN),
      ...counts,
      "GET /api/services": ok([service("ISSUE CROWN", "CROWN"), service("XYZ", "NEWGROUP")]),
      "PATCH /api/services/XYZ": ok(service("XYZ", "NEWGROUP")),
    });
    renderApp("/settings/services");
    const user = userEvent.setup();

    const row = (code: string) => screen.getByText(code, { selector: "strong" }).closest("tr")!;

    await screen.findByText("ISSUE CROWN", { selector: "strong" });
    await user.click(within(row("ISSUE CROWN")).getByRole("button", { name: "Edit" }));
    expect(within(row("ISSUE CROWN")).getByLabelText("Treatment group")).toHaveValue("CROWN");
    await user.click(within(row("ISSUE CROWN")).getByRole("button", { name: "Cancel" }));

    await user.click(within(row("XYZ")).getByRole("button", { name: "Edit" }));
    expect(within(row("XYZ")).getByLabelText("Treatment group")).toHaveValue("NEWGROUP");
    await user.click(within(row("XYZ")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ treatment_group: "NEWGROUP" });
  });
});

describe("requests", () => {
  it("confirms with the GPiS AppointmentID", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    let confirmed = false;
    const { calls } = fakeApi({
      "GET /api/auth/me": ok(STAFF),
      "GET /api/conversations?mode=HUMAN": ok([]),
      "GET /api/requests?status=PENDING": () =>
        ok(confirmed ? [] : [fakeRequest({ group_id: "g1" }), fakeRequest({ id: 2, customer_name: "Demo Kid B", group_id: "g1" })]),
      "POST /api/requests/1/confirm": (body) => {
        confirmed = true;
        return ok(fakeRequest({ status: "CONFIRMED", gpis_appointment_id: (body as { gpis_appointment_id: number }).gpis_appointment_id }));
      },
    });
    renderApp("/requests");
    const user = userEvent.setup();
    const card = (await screen.findByText("Demo Kid A", { selector: "strong" })).closest("li")!;
    expect(within(card).getByText("Demo Kid B")).toBeInTheDocument(); // Together with
    expect(within(card).getByText("Fri 09 Oct 2026 16:00")).toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: "Confirm" }));
    await user.type(within(card).getByLabelText(/GPiS AppointmentID/), "123456");
    await user.click(within(card).getByRole("button", { name: /confirm$/ }));
    await waitFor(() => expect(screen.getByText("No pending requests.")).toBeInTheDocument());
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ gpis_appointment_id: 123456 });
  });

  it("confirms without an ID when the field is empty", async () => {
    const { calls } = fakeApi({
      "GET /api/auth/me": ok(STAFF),
      ...counts,
      "GET /api/requests?status=PENDING": ok([fakeRequest()]),
      "POST /api/requests/1/confirm": ok(fakeRequest({ status: "CONFIRMED" })),
    });
    renderApp("/requests");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Confirm" }));
    await user.click(screen.getByRole("button", { name: /confirm$/ }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ gpis_appointment_id: null });
  });

  it("shows the server's reason when a change is refused", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fakeApi({
      "GET /api/auth/me": ok(STAFF),
      ...counts,
      "GET /api/requests?status=PENDING": ok([fakeRequest()]),
      "POST /api/requests/1/reject": err(409, "A CONFIRMED request cannot be changed like this"),
    });
    renderApp("/requests");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Reject" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("cannot be changed");
  });

  it("does nothing when the staff member says no", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const { calls } = fakeApi({
      "GET /api/auth/me": ok(STAFF),
      ...counts,
      "GET /api/requests?status=PENDING": ok([fakeRequest()]),
    });
    renderApp("/requests");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Reject" }));
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });
});

describe("conversations", () => {
  it("shows the messages and lets staff take over", async () => {
    let mode: "BOT" | "HUMAN" = "BOT";
    const { calls } = fakeApi({
      "GET /api/auth/me": ok(STAFF),
      "GET /api/requests?status=PENDING": ok([]),
      "GET /api/conversations?mode=HUMAN": () => ok(mode === "HUMAN" ? [fakeConversation({ mode })] : []),
      "GET /api/conversations": () => ok([fakeConversation({ mode })]),
      "GET /api/conversations/5": () =>
        ok(fakeConversation({ mode, assigned_staff_name: mode === "HUMAN" ? "Demo Amy" : null })),
      "POST /api/conversations/5/take-over": () => {
        mode = "HUMAN";
        return ok(fakeConversation({ mode }));
      },
    });
    renderApp("/conversations/5");
    expect(await screen.findByText("Hi, can I book scaling?")).toBeInTheDocument();
    expect(screen.getByText("The AI is replying to this conversation.")).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Take over" }));
    expect(await screen.findByText(/Staff is handling this conversation \(Demo Amy\)/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hand back to AI" })).toBeInTheDocument();
    // 选单上的数字马上更新，不用等 30 秒
    expect(await screen.findByRole("link", { name: "Conversations 1" })).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/conversations/5/take-over")).toBe(true);
  });
});

describe("replying to the patient", () => {
  it("sends the reply and shows its delivery status", async () => {
    let replied = false;
    const sent = fakeConversation({ mode: "HUMAN", assigned_staff_name: "Demo Amy" });
    sent.messages.push({
      id: 3, sender: "STAFF", staff_id: 2, body: "See you Friday!", wa_status: "DELIVERED", wa_error: null,
      created_at: "2026-10-06T02:00:00Z",
    });
    const { calls } = fakeApi({
      "GET /api/auth/me": ok(STAFF),
      ...counts,
      "GET /api/conversations": ok([fakeConversation()]),
      "GET /api/conversations/5": () => ok(replied ? sent : fakeConversation()),
      "POST /api/conversations/5/reply": () => {
        replied = true;
        return ok(sent);
      },
    });
    renderApp("/conversations/5");
    const user = userEvent.setup();
    const box = await screen.findByLabelText("Reply on WhatsApp");
    expect(screen.getByText(/Replying takes over this conversation from the AI/)).toBeInTheDocument();

    await user.type(box, "See you Friday!");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/Delivered/)).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ body: "See you Friday!" });
    expect(screen.getByLabelText("Reply on WhatsApp")).toHaveValue(""); // 送出后清空
  });

  it("keeps the text and shows why when WhatsApp refuses", async () => {
    fakeApi({
      "GET /api/auth/me": ok(STAFF),
      ...counts,
      "GET /api/conversations": ok([fakeConversation()]),
      "GET /api/conversations/5": ok(fakeConversation()),
      "POST /api/conversations/5/reply": err(502, "WhatsApp did not accept the message: Recipient not in allowed list"),
    });
    renderApp("/conversations/5");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Reply on WhatsApp"), "Hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Recipient not in allowed list");
    expect(screen.getByLabelText("Reply on WhatsApp")).toHaveValue("Hello"); // 没送出去：字还在
  });

  it("explains the 24-hour rule instead of showing the reply box", async () => {
    fakeApi({
      "GET /api/auth/me": ok(STAFF),
      ...counts,
      "GET /api/conversations": ok([fakeConversation()]),
      "GET /api/conversations/5": ok(fakeConversation({ reply_window_ends_at: "2026-10-01T00:00:00Z" })),
    });
    renderApp("/conversations/5");
    expect(await screen.findByText(/More than 24 hours since the patient's last message/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Reply on WhatsApp")).not.toBeInTheDocument();
  });

  it("shows why a message was not delivered", async () => {
    const c = fakeConversation({ mode: "HUMAN" });
    c.messages.push({
      id: 3, sender: "STAFF", staff_id: 2, body: "Hello", wa_status: "FAILED",
      wa_error: "131047: Re-engagement message", created_at: "2026-10-06T02:00:00Z",
    });
    fakeApi({
      "GET /api/auth/me": ok(STAFF),
      ...counts,
      "GET /api/conversations": ok([c]),
      "GET /api/conversations/5": ok(c),
    });
    renderApp("/conversations/5");
    expect(await screen.findByText(/Not delivered/)).toBeInTheDocument();
    expect(screen.getByText("131047: Re-engagement message")).toBeInTheDocument();
  });
});

describe("menu (hamburger)", () => {
  const routes = {
    "GET /api/auth/me": ok(STAFF),
    ...counts,
    "GET /api/requests?status=PENDING": ok([]),
  };

  it("collapses the menu to icons on a computer screen and remembers it", async () => {
    fakeApi(routes);
    renderApp("/account");
    const user = userEvent.setup();
    const collapse = await screen.findByRole("button", { name: "Collapse menu" });
    expect(collapse).toHaveAttribute("aria-expanded", "true");

    await user.click(collapse);
    const expand = screen.getByRole("button", { name: "Expand menu" });
    expect(expand).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("link", { name: "Reminders" })).toHaveAttribute("title", "Reminders"); // 只有图示时滑过看得到名字
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument(); // 读屏软件还是念得到
    expect(localStorage.getItem("clinicAdmin.menuCollapsed")).toBe("1");

    await user.click(expand);
    expect(screen.getByRole("button", { name: "Collapse menu" })).toHaveAttribute("aria-expanded", "true");
    expect(localStorage.getItem("clinicAdmin.menuCollapsed")).toBe("0");
  });

  it("opens the menu on a narrow screen and closes it after choosing a page", async () => {
    fakeApi(routes);
    renderApp("/account");
    const user = userEvent.setup();
    const open = await screen.findByRole("button", { name: "Open menu" });
    expect(open).toHaveAttribute("aria-expanded", "false");

    await user.click(open);
    expect(open).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Close menu" })).toHaveFocus();

    await user.click(screen.getByRole("link", { name: "Requests" }));
    expect(await screen.findByRole("heading", { name: "Appointment requests" })).toBeInTheDocument();
    expect(open).toHaveAttribute("aria-expanded", "false");
  });

  it("closes the narrow-screen menu with Escape", async () => {
    fakeApi(routes);
    renderApp("/account");
    const user = userEvent.setup();
    const open = await screen.findByRole("button", { name: "Open menu" });
    await user.click(open);
    await user.keyboard("{Escape}");
    expect(open).toHaveAttribute("aria-expanded", "false");
    expect(open).toHaveFocus();
  });
});
