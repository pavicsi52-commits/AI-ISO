"use client";

import { useEffect } from "react";

import { resolveTheme, useThemeStore } from "@/stores/theme-store";

/**
 * Applies the resolved theme (light/dark, respecting "system") to the root
 * `<html>` element and keeps it in sync with OS preference changes.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useThemeStore((state) => state.theme);

  useEffect(() => {
    const root = document.documentElement;

    const applyResolvedTheme = () => {
      const resolved = resolveTheme(theme);
      root.classList.toggle("dark", resolved === "dark");
      root.style.colorScheme = resolved;
    };

    applyResolvedTheme();

    if (theme !== "system") return;

    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", applyResolvedTheme);
    return () => media.removeEventListener("change", applyResolvedTheme);
  }, [theme]);

  return children;
}
