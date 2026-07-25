import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ThemeToggle } from "@/components/ui/theme-toggle";
import { useThemeStore } from "@/stores/theme-store";

function mockMatchMedia(matches: boolean) {
  window.matchMedia = vi.fn().mockReturnValue({
    matches,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
}

describe("ThemeToggle", () => {
  afterEach(() => {
    useThemeStore.setState({ theme: "system" });
  });

  it("switches from light to dark when clicked", () => {
    useThemeStore.setState({ theme: "light" });
    render(<ThemeToggle />);

    screen.getByRole("button", { name: "Toggle theme" }).click();

    expect(useThemeStore.getState().theme).toBe("dark");
  });

  it("switches from dark to light when clicked", () => {
    useThemeStore.setState({ theme: "dark" });
    render(<ThemeToggle />);

    screen.getByRole("button", { name: "Toggle theme" }).click();

    expect(useThemeStore.getState().theme).toBe("light");
  });

  it("resolves 'system' before deciding which way to toggle", () => {
    mockMatchMedia(true);
    useThemeStore.setState({ theme: "system" });
    render(<ThemeToggle />);

    screen.getByRole("button", { name: "Toggle theme" }).click();

    expect(useThemeStore.getState().theme).toBe("light");
  });
});
