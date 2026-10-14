import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Shop Floor Video Agent",
  description: "AI agent that finds safety events in factory floor videos.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col bg-zinc-50 font-sans text-zinc-900">
        {children}
      </body>
    </html>
  );
}
