import { Sidebar } from "@/components/layout/sidebar";
import { CommandPalette } from "@/components/layout/command-palette";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-dvh overflow-hidden pb-16 md:pb-0">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <main className="min-w-0 flex-1 overflow-auto p-0">{children}</main>
      </div>
      <CommandPalette />
    </div>
  );
}
