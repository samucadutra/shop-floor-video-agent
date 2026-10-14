"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const LINKS = [
  { href: "/videos", label: "Videos" },
  { href: "/upload", label: "Upload" },
];

function Brand() {
  return (
    <Link href="/videos" className="font-semibold tracking-tight text-zinc-900">
      Shop Floor Video Agent
    </Link>
  );
}

/** Rendered while the pathname is not known yet (prerendering). */
export function NavFallback() {
  return (
    <header className="border-b border-zinc-200 bg-white">
      <div className="mx-auto flex h-14 max-w-6xl items-center px-4">
        <Brand />
      </div>
    </header>
  );
}

export default function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  const link = (href: string, label: string, extra = "") => {
    const active = pathname === href || pathname.startsWith(`${href}/`);
    return (
      <Link
        key={href}
        href={href}
        onClick={() => setOpen(false)}
        aria-current={active ? "page" : undefined}
        className={`rounded-md px-3 py-2 text-sm font-medium ${extra} ${
          active ? "bg-zinc-900 text-white" : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900"
        }`}
      >
        {label}
      </Link>
    );
  };

  return (
    <header className="border-b border-zinc-200 bg-white">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
        <Brand />
        <nav className="hidden gap-1 sm:flex">{LINKS.map((l) => link(l.href, l.label))}</nav>
        <button
          type="button"
          className="rounded-md p-2 text-zinc-600 hover:bg-zinc-100 sm:hidden"
          aria-label="Toggle menu"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5" aria-hidden>
            <path d="M3 5h14v2H3zM3 9h14v2H3zM3 13h14v2H3z" />
          </svg>
        </button>
      </div>
      {open && (
        <nav className="flex flex-col gap-1 border-t border-zinc-200 px-4 py-2 sm:hidden">
          {LINKS.map((l) => link(l.href, l.label, "block"))}
        </nav>
      )}
    </header>
  );
}
