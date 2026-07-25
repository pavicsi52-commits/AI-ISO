import { describe, expect, it } from "vitest";

import { cn } from "@/utils/cn";

describe("cn", () => {
  it("joins truthy string values with a space", () => {
    expect(cn("a", "b", "c")).toBe("a b c");
  });

  it("skips falsy values", () => {
    expect(cn("a", false, undefined, null, "", "b")).toBe("a b");
  });

  it("flattens nested arrays", () => {
    expect(cn("a", ["b", "c"], ["d", ["e"]])).toBe("a b c d e");
  });

  it("returns an empty string when nothing is truthy", () => {
    expect(cn(false, undefined, null)).toBe("");
  });
});
