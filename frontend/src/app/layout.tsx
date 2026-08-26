import type { Metadata } from "next";
import "./globals.css";
import { WorkspaceSettingsHost } from "./workspace-settings-host";

export const metadata: Metadata = {
  title: "Signaldesk | Intelligence workspace",
  description: "Multi-source intelligence and monitoring operations workspace.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ar" dir="rtl" suppressHydrationWarning>
      <body>{children}<WorkspaceSettingsHost /></body>
    </html>
  );
}
