import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "PersonalOps AI",
  description: "AI Operations Agent Platform — admin dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
          background: "#0f1117",
          color: "#e6e8eb",
          minHeight: "100vh",
        }}
      >
        {children}
      </body>
    </html>
  );
}
