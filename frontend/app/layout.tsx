import type { Metadata } from "next";
import { Suspense } from "react";
import Nav, { NavFallback } from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Shop Floor Video Agent",
  description: "AI agent that finds safety events in factory floor videos.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col bg-zinc-50 font-sans text-zinc-900">
        {/* usePathname suspends on dynamic routes, so the nav has its own boundary. */}
        <Suspense fallback={<NavFallback />}>
          <Nav />
        </Suspense>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:py-8">{children}</main>
      </body>
    </html>
  );
}
