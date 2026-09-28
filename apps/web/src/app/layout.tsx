import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { MemorySessionProvider } from "@/components/memory/memory-session-provider";
import { AuthProvider } from "@/lib/auth/auth-context";
import { WorkspaceProvider } from "@/lib/workspace-context";
import { ThemeProvider } from "@/lib/theme-context";
import { I18nProvider } from "@/lib/i18n-context";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const themeInitScript = `(() => {
  try {
    const key = "ai_pdf_workspace_theme";
    const saved = localStorage.getItem(key);
    const theme = saved === "light" || saved === "dark" ? saved : "dark";
    document.documentElement.classList.toggle("dark", theme === "dark");
  } catch {
    document.documentElement.classList.add("dark");
  }
})();`;

export const metadata: Metadata = {
  title: "Citeframe",
  description: "A multi-workspace text PDF knowledge workspace.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="min-h-full bg-background text-foreground transition-colors duration-200">
        <I18nProvider>
          <ThemeProvider>
            <AuthProvider>
              <WorkspaceProvider><MemorySessionProvider>{children}</MemorySessionProvider></WorkspaceProvider>
            </AuthProvider>
          </ThemeProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
