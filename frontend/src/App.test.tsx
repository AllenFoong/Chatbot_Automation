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
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument(); // 还不能回复（D28）

    await userEvent.setup().click(screen.getByRole("button", { name: "Take over" }));
    expect(await screen.findByText(/Staff is handling this conversation \(Demo Amy\)/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hand back to AI" })).toBeInTheDocument();
    // 选单上的数字马上更新，不用等 30 秒
    expect(await screen.findByRole("link", { name: "Conversations 1" })).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/conversations/5/take-over")).toBe(true);
  });
});
