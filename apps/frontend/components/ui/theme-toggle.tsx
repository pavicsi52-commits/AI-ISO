"use client";

import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { resolveTheme, useThemeStore } from "@/stores/theme-store";

export function ThemeToggle() {
  const theme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.setTheme);
  const resolved = resolveTheme(theme);

  return (
    <Button
      variant="ghost"
      aria-label="Toggle theme"
      onClick={() => setTheme(resolved === "dark" ? "light" : "dark")}
    >
      {resolved === "dark" ? (
        <Sun className="size-4" aria-hidden="true" />
      ) : (
        <Moon className="size-4" aria-hidden="true" />
      )}
    </Button>
  );
}
