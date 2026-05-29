import { describe, expect, it } from "vitest";
import {
  sortDirectionForColumn,
  sortKeyForColumn,
} from "./historyDisplay";

describe("history sortable columns", () => {
  it("toggles ticker sort direction", () => {
    expect(sortKeyForColumn("ticker", "ticker_desc")).toBe("ticker_asc");
    expect(sortKeyForColumn("ticker", "ticker_asc")).toBe("ticker_desc");
    expect(sortDirectionForColumn("ticker", "ticker_desc")).toBe("desc");
  });
});
