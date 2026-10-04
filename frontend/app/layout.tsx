import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "PersonalOps AI",
  description: "AI Operations Agent Platform — admin dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // suppressHydrationWarning on <html>/<body> only: browser extensions
    // (Grammarly, ColorZilla, etc.) inject attributes like
    // data-gr-ext-installed / cz-shortcut-listen into these tags before
    // React hydrates, causing a harmless server/client mismatch warning
    // Next.js explicitly documents as extension-caused. This does not
    // suppress hydration warnings for anything else in the tree.
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <AuthProvider>
          <Nav />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
