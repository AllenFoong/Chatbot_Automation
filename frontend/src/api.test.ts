import { describe, expect, it, vi } from "vitest";
import { ApiError, auth, errorMessage, explainDuplicate, requests, setUnauthorizedHandler, settings } from "./api";
import { err, fakeApi, ok } from "./test/fakeApi";

describe("errorMessage", () => {
  it("uses the detail text", () => {
    expect(errorMessage(401, { detail: "Wrong username or password" })).toBe("Wrong username or password");
  });

  it("adds the database rule name", () => {
    expect(errorMessage(422, { detail: "Rejected by a database rule", rule: "ck_x" })).toBe(
      "Rejected by a database rule (ck_x)",
    );
  });

  it("lists FastAPI validation errors with the field", () => {
    const body = { detail: [{ loc: ["body", "closure_date"], msg: "Input should be a valid date" }] };
    expect(errorMessage(422, body)).toBe("closure_date: Input should be a valid date");
  });

  it("explains a server that is not running", () => {
    expect(errorMessage(502, null)).toMatch(/backend/);
  });
});

describe("request", () => {
  it("calls the unauthorized handler on 401", async () => {
    fakeApi({ "GET /api/requests?status=PENDING": err(401, "Please log in") });
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    await expect(requests.list("PENDING")).rejects.toThrow("Please log in");
    expect(handler).toHaveBeenCalledOnce();
    setUnauthorizedHandler(null);
  });

  it("does not treat a failed login as an expired session", async () => {
    fakeApi({ "POST /api/auth/login": err(401, "Wrong username or password") });
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    await expect(auth.login("boss", "x")).rejects.toBeInstanceOf(ApiError);
    expect(handler).not.toHaveBeenCalled();
    setUnauthorizedHandler(null);
  });

  it("returns nothing for 204", async () => {
    fakeApi({ "DELETE /api/closures/2026-02-16": { status: 204 } });
    await expect(settings.deleteClosure("2026-02-16")).resolves.toBeUndefined();
  });

  it("encodes treatment codes with / and +", async () => {
    const { calls } = fakeApi({
      "PATCH /api/services/C%2FUP": ok({}),
      "PATCH /api/services/S%2BP": ok({}),
    });
    await settings.updateService("C/UP", { name: "Check up" });
    await settings.updateService("S+P", { active: false });
    expect(calls.map((c) => c.path)).toEqual(["/api/services/C%2FUP", "/api/services/S%2BP"]);
    expect(calls[0]?.body).toEqual({ name: "Check up" });
  });

  it("reports a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(auth.me()).rejects.toThrow(/Cannot reach the server/);
  });
});

describe("explainDuplicate", () => {
  it("replaces a 409 message", async () => {
    await expect(explainDuplicate(Promise.reject(new ApiError(409, "Already exists")), "Taken.")).rejects.toThrow(
      "Taken.",
    );
  });

  it("keeps other errors", async () => {
    await expect(explainDuplicate(Promise.reject(new ApiError(422, "Bad")), "Taken.")).rejects.toThrow("Bad");
  });
});
