import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("mounts dashboard route", async () => {
    const el = document.createElement("div");
    document.body.appendChild(el);
    act(() => {
      createRoot(el).render(
        <StrictMode>
          <MemoryRouter initialEntries={["/dashboard"]}>
            <App />
          </MemoryRouter>
        </StrictMode>
      );
    });
    await waitFor(() => {
      expect(el.innerHTML).toContain("Main analysis");
    });
  });
});
