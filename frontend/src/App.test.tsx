import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("mounts dashboard route", () => {
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
    expect(el.innerHTML).toContain("Main analysis");
  });
});
