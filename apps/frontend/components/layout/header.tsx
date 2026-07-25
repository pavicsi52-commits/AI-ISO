import { ThemeToggle } from "@/components/ui/theme-toggle";

export function Header() {
  return (
    <header className="border-border flex h-14 items-center justify-between border-b px-6">
      <span className="text-sm font-semibold tracking-tight">AI-IOS</span>
      <ThemeToggle />
    </header>
  );
}
