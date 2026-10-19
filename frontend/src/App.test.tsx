import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ADMIN, STAFF, err, fakeApi, fakeChoices, fakeConversation, fakeRequest, ok } from "./test/fakeApi";
import { renderApp } from "./test/render";

// 选单上的数字（每个画面都会读）
const counts = {
  "GET /api/conversations?mode=HUMAN": ok([]),
  "GET /api/requests?to_tell=true": ok([]),
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

  it("shows the password only while the eye is pressed", async () => {
    fakeApi({ "GET /api/auth/me": err(401, "Please log in") });
    renderApp("/requests");
    const user = userEvent.setup();
    const password = await screen.findByLabelText("Password");
    await user.type(password, "secret-123");
    expect(password).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password).toHaveAttribute("type", "password");
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
      "GET /api/requests?to_tell=true": ok([]),
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

describe("auto-confirm (D71 ②)", () => {
  const settings = { max_per_slot: 3, max_per_slot_for_ai: 3, clinic_contact_id: 34094, auto_confirm: false };
  const status = {
    enabled: true,
    runs_here: true,
    source: "GPiS",
    checked_at: "2026-10-19T03:00:00Z",
    error: null,
    in_business_hours: true,
    stale: false,
  };

  it("only ADMIN can switch it on in Settings", async () => {
    const { calls } = fakeApi({
      "GET /api/auth/me": ok(ADMIN),
      ...counts,
      "GET /api/settings": ok(settings),
      "PATCH /api/settings": (body) => ok({ ...settings, ...(body as object) }),
    });
    renderApp("/settings/clinic");
    const user = userEvent.setup();
    const box = await screen.findByRole("switch", { name: "Confirm matching requests automatically" });
    expect(box).not.toBeChecked();
    expect(screen.getByText("Off")).toBeInTheDocument();
    // 关的时候没有说明
    expect(screen.queryByText(/Off by default/)).toBeNull();
    expect(screen.queryByText("Press Save to apply.")).toBeNull();
    await user.click(box);
    expect(screen.getByText("On")).toBeInTheDocument();
    expect(screen.getByText(/Off by default/)).toBeInTheDocument();
    expect(screen.getByText("Press Save to apply.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(screen.queryByText("Press Save to apply.")).toBeNull();
    expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ auto_confirm: true });
    // 拨回关、还没 Save：说明不见了，但还是提醒要 Save
    await user.click(box);
    expect(screen.queryByText(/Off by default/)).toBeNull();
    expect(screen.getByText("Press Save to apply.")).toBeInTheDocument();
  });

  it("STAFF sees the switch but cannot change it", async () => {
    fakeApi({ "GET /api/auth/me": ok(STAFF), ...counts, "GET /api/settings": ok({ ...settings, auto_confirm: true }) });
    renderApp("/settings/clinic");
    const box = await screen.findByRole("switch", { name: "Confirm matching requests automatically" });
    expect(box).toBeChecked();
    expect(box).toBeDisabled();
    expect(screen.getByText(/Off by default/)).toBeInTheDocument();
    expect(screen.queryByText("Press Save to apply.")).toBeNull();
  });

  it.each([
    [{ ...status, enabled: false }, /Auto-confirm is off: press Entered in GPiS/],
    [status, /Auto-confirm is on: requests that match GPiS exactly are confirmed automatically\. Last checked GPiS/],
    [{ ...status, runs_here: false, source: "GPiS_Dev" }, /does not run with GPiS_Dev/],
    [{ ...status, stale: true, error: "Could not check GPiS (OperationalError)." }, /has not checked GPiS since/],
  ])("shows whether it is working on the Requests page (%#)", async (s, text) => {
    fakeApi({
      "GET /api/auth/me": ok(STAFF),
      ...counts,
      "GET /api/requests?status=PENDING": ok([]),
      "GET /api/requests/auto-confirm": ok(s),
    });
    renderApp("/requests");
    expect(await screen.findByText(text)).toBeInTheDocument();
  });

  it("marks requests confirmed by auto-confirm", async () => {
    fakeApi({
      "GET /api/auth/me": ok(STAFF),
      ...counts,
      "GET /api/requests?status=PENDING": ok([]),
      "GET /api/requests/auto-confirm": ok(status),
      "GET /api/requests?status=CONFIRMED": ok([
        fakeRequest({ status: "CONFIRMED", handled_by: null, patient_told_at: "2026-10-19T03:03:00Z" }),
      ]),
    });
    renderApp("/requests");
    await userEvent.setup().click(await screen.findByRole("tab", { name: "Confirmed" }));
    expect(await screen.findByText("Auto-confirm (matched GPiS)")).toBeInTheDocument();
  });
});

describe("staff accounts", () => {
  const boss = { ...ADMIN };
  const typo = { id: 9, username: "typo", name: "Typo", role: "STAFF" as const, active: true };
  const amy = { ...STAFF };

  it("deletes an unused account and explains why a used one cannot be deleted", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    let deleted = false;
    const { calls } = fakeApi({
      "GET /api/auth/me": ok(ADMIN),
      ...counts,
      "GET /api/staff": () => ok(deleted ? [boss, amy] : [boss, amy, typo]),
      "DELETE /api/staff/9": () => {
        deleted = true;
        return { status: 204 };
      },
      "DELETE /api/staff/2": err(409, "amy has sent messages. Deactivate the account instead, so the history still shows who did it."),
    });
    renderApp("/staff");
    const user = userEvent.setup();
    const typoRow = (await screen.findByText("typo")).closest("tr")!;
    const bossRow = screen.getByText("boss").closest("tr")!;
    expect(within(bossRow).queryByRole("button", { name: "Delete" })).toBeNull(); // 自己的不能删
    await user.click(within(typoRow).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByText("typo")).toBeNull());
    expect(calls.some((c) => c.method === "DELETE" && c.path === "/api/staff/9")).toBe(true);

    const amyRow = screen.getByText("amy").closest("tr")!;
    await user.click(within(amyRow).getByRole("button", { name: "Delete" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Deactivate the account instead");
    expect(alert.closest("tr")?.previousElementSibling).toBe(amyRow); // 在 amy 那一行的下面
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
  it("confirms by picking the appointment read from GPiS", async () => {
    let confirmed = false;
    const { calls } = fakeApi({
      "GET /api/auth/me": ok(STAFF),
      "GET /api/conversations?mode=HUMAN": ok([]),
      "GET /api/requests?to_tell=true": ok([]),
      "GET /api/requests?status=PENDING": () =>
        ok(confirmed ? [] : [fakeRequest({ group_id: "g1" }), fakeRequest({ id: 2, customer_name: "Demo Kid B", group_id: "g1" })]),
      "GET /api/requests/1/gpis?date=2026-10-09": ok(fakeChoices()),
      "GET /api/requests/1/gpis?date=2026-10-10": ok(fakeChoices({ date: "2026-10-10", choices: [] })),
      "POST /api/requests/1/confirm": () => {
        confirmed = true;
        return ok(fakeRequest({ status: "CONFIRMED", gpis_appointment_id: 101, patient_told_at: "2026-10-06T02:00:00Z" }));
      },
    });
    renderApp("/requests");
    const user = userEvent.setup();
    const card = (await screen.findByText("Demo Kid A", { selector: "strong" })).closest("li")!;
    expect(within(card).getByText("Demo Kid B")).toBeInTheDocument(); // Together with
    expect(within(card).getByText("Fri 09 Oct 2026 16:00")).toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: "Entered in GPiS ✓" }));
    // 在画面中间弹出视窗（不在卡片里）
    const dialog = await screen.findByRole("dialog", { name: "Entered in GPiS – Demo Kid A" });
    expect(card).not.toContainElement(dialog);
    const pick = within(dialog).getByRole("button", { name: "Confirm this appointment" });
    expect(pick).toBeDisabled(); // 要先点选
    const radios = await within(dialog).findAllByRole("radio");
    expect(radios.map((r) => r.closest("label")!.textContent)).toEqual([
      "16:00 DEMO KID A · Dr PHANGSame doctor · Same time",
      "10:00 SOMEONE ELSE · Dr GOH",
      "16:00 DEMO KID B · Dr PHANGSame doctor · Same time · already confirms request #7",
    ]);
    expect(radios[2]!).toBeDisabled(); // 已经确认了别的请求

    // 换日期 → 重新读 GPiS；那天没有就说要先在 GPiS 输入
    const date = within(dialog).getByLabelText("GPiS date");
    await user.clear(date);
    await user.type(date, "2026-10-10");
    expect(await within(dialog).findByText(/GPiS has no appointments on/)).toBeInTheDocument();
    await user.clear(date);
    await user.type(date, "2026-10-09");

    await user.click((await within(dialog).findAllByRole("radio"))[0]!);
    await user.click(pick);
    expect(await screen.findByText(/confirmed, and the patient was sent the confirmation/)).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ gpis_appointment_id: 101, date: "2026-10-09" });
    await waitFor(() => expect(screen.getByText("No pending requests.")).toBeInTheDocument());
  });

  it("warns when the list comes from GPiS_Dev and shows why the patient was not messaged", async () => {
    fakeApi({
      "GET /api/auth/me": ok(STAFF),
      ...counts,
      "GET /api/requests?status=PENDING": ok([fakeRequest()]),
      "GET /api/requests/1/gpis?date=2026-10-09": ok(fakeChoices({ source: "GPiS_Dev", can_notify: false })),
      "POST /api/requests/1/confirm": ok(
        fakeRequest({ status: "CONFIRMED", notify_problem: "Not sent: the GPiS list comes from GPiS_Dev" }),
      ),
    });
    renderApp("/requests");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Entered in GPiS ✓" }));
    expect(await screen.findByText(/comes from GPiS_Dev: the patient will not be messaged/)).toBeInTheDocument();
    await user.click((await screen.findAllByRole("radio"))[0]!);
    await user.click(screen.getByRole("button", { name: "Confirm this appointment" }));
    expect(await screen.findByText(/confirmed, but the patient was not messaged/)).toHaveTextContent(
      "Not sent: the GPiS list comes from GPiS_Dev",
    );
  });

  it("shows GPiS errors and lets staff go back", async () => {
    const { calls } = fakeApi({
      "GET /api/auth/me": ok(STAFF),
      ...counts,
      "GET /api/requests?status=PENDING": ok([fakeRequest()]),
      "GET /api/requests/1/gpis?date=2026-10-09": err(503, "Could not read GPiS. Please try again."),
    });
    renderApp("/requests");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Entered in GPiS ✓" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not read GPiS");
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    // Esc 也是关掉
    await user.click(screen.getByRole("button", { name: "Entered in GPiS ✓" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("lists patients to tell; the reason, message and Patient told are in a pop-up", async () => {
    let told = false;
    const message = "预约确认✅\nNAME: DEMO KID A";
    const { calls } = fakeApi({
      "GET /api/auth/me": ok(STAFF),
      "GET /api/conversations?mode=HUMAN": ok([]),
      "GET /api/requests?status=PENDING": ok([]),
      "GET /api/requests?to_tell=true": () =>
        ok(
          told
            ? []
            : [
                fakeRequest({
                  status: "CONFIRMED",
                  confirmed_date: "2026-10-09",
                  confirmed_slot: "16:30:00",
                  confirmed_doctor_id: "PHANG",
                  confirm_message: message,
                  notify_problem: "More than 24 hours since the patient's last message",
                  whatsapp_allowed: true,
                }),
                fakeRequest({ id: 2, customer_name: "Demo Kid B", status: "CONFIRMED", confirm_message: message }),
              ],
        ),
      "POST /api/requests/1/patient-told": () => {
        told = true;
        return ok(fakeRequest({ status: "CONFIRMED", patient_told_at: "2026-10-06T02:00:00Z", patient_told_by: 2 }));
      },
    });
    renderApp("/requests");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "To tell patient (2)" }));
    const card = (await screen.findByText("Demo Kid A", { selector: "strong" })).closest("li")!;
    // 卡片只有重要的资讯：GPiS 的日期、时间、医生；原因、消息、按钮都在弹出视窗
    expect(within(card).getByText("Fri 09 Oct 2026 16:30 · Dr PHANG")).toBeInTheDocument();
    expect(within(card).queryByText(/More than 24 hours/)).toBeNull();
    expect(within(card).queryByRole("link", { name: "Open in WhatsApp" })).toBeNull();
    expect(within(card).queryByRole("button", { name: "Patient told ✓" })).toBeNull();

    // 不能 Open in WhatsApp 的（读 GPiS_Dev）：视窗里只有 Patient told；Back 关掉、什么都不改
    const other = screen.getByText("Demo Kid B", { selector: "strong" }).closest("li")!;
    await user.click(within(other).getByRole("button", { name: "Tell the patient" }));
    let dialog = await screen.findByRole("dialog", { name: "Tell the patient – Demo Kid B" });
    expect(within(dialog).getByText(/the system stopped before sending/)).toBeInTheDocument();
    expect(within(dialog).queryByRole("link", { name: "Open in WhatsApp" })).toBeNull();
    await user.click(within(dialog).getByRole("button", { name: "Back" }));
    expect(screen.queryByRole("dialog")).toBeNull();

    await user.click(within(card).getByRole("button", { name: "Tell the patient" }));
    dialog = await screen.findByRole("dialog", { name: "Tell the patient – Demo Kid A" });
    expect(within(dialog).getByText(/More than 24 hours/)).toBeInTheDocument();
    expect(within(dialog).getByText("In GPiS: Fri 09 Oct 2026 16:30 · Dr PHANG · +60120000001")).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Open in WhatsApp" })).toHaveAttribute(
      "href",
      "whatsapp://send?phone=60120000001&text=%E9%A2%84%E7%BA%A6%E7%A1%AE%E8%AE%A4%E2%9C%85%0ANAME%3A%20DEMO%20KID%20A",
    );
    expect(calls.some((c) => c.method === "POST")).toBe(false);

    await user.click(within(dialog).getByRole("button", { name: "Patient told ✓" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(screen.getByText("Every confirmed patient has been told.")).toBeInTheDocument());
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/requests/1/patient-told")).toBe(true);
    expect(screen.getByRole("tab", { name: "To tell patient" })).toBeInTheDocument();
  });

  it("shows the server's reason when a change is refused", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fakeApi({
      "GET /api/auth/me": ok(STAFF),
      ...counts,
      "GET /api/requests?to_tell=true": ok([]),
      "GET /api/requests?status=PENDING": ok([fakeRequest()]),
      "POST /api/requests/1/reject": err(409, "A CONFIRMED request cannot be changed like this"),
    });
    renderApp("/requests");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Reject" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("cannot be changed");
  });

  it("moves a cancelled request back to pending", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    let reopened = false;
    const { calls } = fakeApi({
      "GET /api/auth/me": ok(STAFF),
      ...counts,
      "GET /api/requests?status=CANCELLED": () => ok(reopened ? [] : [fakeRequest({ status: "CANCELLED" })]),
      "POST /api/requests/1/reopen": () => {
        reopened = true;
        return ok(fakeRequest());
      },
    });
    renderApp("/requests");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "Cancelled" }));
    await user.click(await screen.findByRole("button", { name: "Back to pending" }));
    await waitFor(() => expect(screen.getByText("No cancelled requests.")).toBeInTheDocument());
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/requests/1/reopen")).toBe(true);
  });

  it("does nothing when the staff member says no", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const { calls } = fakeApi({
      "GET /api/auth/me": ok(STAFF),
      ...counts,
      "GET /api/requests?to_tell=true": ok([]),
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
      "GET /api/requests?to_tell=true": ok([]),
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
    "GET /api/requests?to_tell=true": ok([]),
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
