import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Recherche d'emploi — Dashboard",
  description: "Offres filtrées et lettres générées chaque nuit.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
