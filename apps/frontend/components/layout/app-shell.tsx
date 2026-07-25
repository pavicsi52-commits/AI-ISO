import { Footer } from "@/components/layout/footer";
import { Header } from "@/components/layout/header";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-background text-foreground flex min-h-screen flex-col">
      <Header />
      <main className="flex-1 p-6">{children}</main>
      <Footer />
    </div>
  );
}
