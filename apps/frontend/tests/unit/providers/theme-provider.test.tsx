import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "@/providers/theme-provider";
import { useThemeStore } from "@/stores/theme-store";

describe("ThemeProvider", () => {
  afterEach(() => {
    useThemeStore.setState({ theme: "system" });
    document.documentElement.classList.remove("dark");
  });

  it("applies the 'dark' class to <html> when the theme is dark", () => {
    useThemeStore.setState({ theme: "dark" });

    render(
      <ThemeProvider>
        <div />
      </ThemeProvider>,
    );

    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("removes the 'dark' class when the theme is light", () => {
    useThemeStore.setState({ theme: "light" });

    render(
      <ThemeProvider>
        <div />
      </ThemeProvider>,
    );

    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(document.documentElement.style.colorScheme).toBe("light");
  });

  it("subscribes to OS preference changes when theme is 'system'", () => {
    const addEventListener = vi.fn();
    const removeEventListener = vi.fn();
    window.matchMedia = vi.fn().mockReturnValue({
      matches: false,
      addEventListener,
      removeEventListener,
    });
    useThemeStore.setState({ theme: "system" });

    const { unmount } = render(
      <ThemeProvider>
        <div />
      </ThemeProvider>,
    );

    expect(addEventListener).toHaveBeenCalledWith("change", expect.any(Function));

    unmount();

    expect(removeEventListener).toHaveBeenCalledWith("change", expect.any(Function));
  });
});
