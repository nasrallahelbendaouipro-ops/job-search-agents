import Link from "next/link";

import { SignOutButton } from "@/components/sign-out-button";

const NAV = [
  { href: "/", label: "Aujourd'hui" },
  { href: "/historique", label: "Historique" },
  { href: "/criteres", label: "Critères" },
  { href: "/liens", label: "Liens manuels" },
  { href: "/runs", label: "Exécutions" },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
          <Link href="/" className="text-lg font-semibold text-brand">
            Recherche d&apos;emploi
          </Link>
          <nav className="flex flex-1 gap-1">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="rounded-md px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <SignOutButton />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
  );
}
