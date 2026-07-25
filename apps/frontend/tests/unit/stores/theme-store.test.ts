import { afterEach, describe, expect, it, vi } from "vitest";

import { resolveTheme, useThemeStore } from "@/stores/theme-store";

function mockMatchMedia(matches: boolean) {
  window.matchMedia = vi.fn().mockReturnValue({
    matches,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
}

describe("useThemeStore", () => {
  afterEach(() => {
    useThemeStore.setState({ theme: "system" });
  });

  it("defaults to system theme", () => {
    expect(useThemeStore.getState().theme).toBe("system");
  });

  it("updates the theme via setTheme", () => {
    useThemeStore.getState().setTheme("dark");

    expect(useThemeStore.getState().theme).toBe("dark");
  });
});

describe("resolveTheme", () => {
  it("returns the explicit theme when not 'system'", () => {
    expect(resolveTheme("dark")).toBe("dark");
    expect(resolveTheme("light")).toBe("light");
  });

  it("resolves 'system' to dark when the OS prefers dark", () => {
    mockMatchMedia(true);

    expect(resolveTheme("system")).toBe("dark");
  });

  it("resolves 'system' to light when the OS prefers light", () => {
    mockMatchMedia(false);

    expect(resolveTheme("system")).toBe("light");
  });
});
