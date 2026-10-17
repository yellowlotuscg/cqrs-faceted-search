import { describe, expect, it } from "vitest";
import { pageTitle } from "./App";

describe("search UI", () => {
  it("has a catalog title", () => {
    expect(pageTitle).toBe("Equipment manual search");
  });
});
