import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api";
import { NotificationSettingsPage } from "./NotificationSettingsPage";

describe("NotificationSettingsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "fetchNotificationConfig").mockResolvedValue({
      enabled: false,
      quiet_hours_start: null,
      quiet_hours_end: null,
      channels: [],
      dedupe_minutes: 15,
    });
    vi.spyOn(api, "putNotificationConfig").mockImplementation(async (cfg) => cfg);
    vi.spyOn(api, "testNotificationChannel").mockResolvedValue({ ok: true });
  });

  it("renders global settings and add channel buttons", async () => {
    const el = document.createElement("div");
    document.body.appendChild(el);
    await act(async () => {
      createRoot(el).render(
        <StrictMode>
          <MemoryRouter initialEntries={["/settings/notifications"]}>
            <NotificationSettingsPage />
          </MemoryRouter>
        </StrictMode>
      );
    });
    expect(el.textContent).toContain("Notifications");
    expect(el.textContent).toContain("Enable notifications");
    expect(el.textContent).toContain("Webhook");
  });
});
