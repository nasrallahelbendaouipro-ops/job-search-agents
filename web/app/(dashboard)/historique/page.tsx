import Link from "next/link";

import { createClient } from "@/lib/supabase/server";
import {
  APPLICATION_STATUS_LABELS,
  APPLICATION_STATUS_STYLES,
  formatDateTime,
  type ApplicationWithOffer,
} from "@/lib/types";

export const dynamic = "force-dynamic";

const FILTERS = [
  { value: "all", label: "Toutes" },
  { value: "sent", label: "Envoyées" },
  { value: "rejected", label: "Écartées" },
  { value: "to_validate", label: "À valider" },
  { value: "manual_required", label: "Action manuelle" },
] as const;

export default async function HistoryPage({
  searchParams,
}: {
  searchParams: Promise<{ statut?: string }>;
}) {
  const { statut = "all" } = await searchParams;
  const supabase = await createClient();

  let query = supabase
    .from("applications")
    .select("*, offer:offers(*)")
    .order("created_at", { ascending: false })
    .limit(200);

  if (statut !== "all") {
    query = query.eq("status", statut);
  }

  const { data, error } = await query;
  const applications = (data ?? []) as unknown as ApplicationWithOffer[];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Historique</h1>
        <p className="mt-1 text-sm text-slate-600">
          Toutes les candidatures, toutes sources confondues.
        </p>
      </header>

      <nav className="flex flex-wrap gap-2">
        {FILTERS.map((filter) => (
          <Link
            key={filter.value}
            href={`/historique?statut=${filter.value}`}
            className={
              statut === filter.value
                ? "badge bg-brand text-white"
                : "badge bg-slate-200 text-slate-700 hover:bg-slate-300"
            }
          >
            {filter.label}
          </Link>
        ))}
      </nav>

      {error && <p className="card text-sm text-rose-600">{error.message}</p>}

      {applications.length === 0 ? (
        <p className="card text-sm text-slate-600">Aucune candidature à afficher.</p>
      ) : (
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Poste</th>
                <th className="px-4 py-2 font-medium">Entreprise</th>
                <th className="px-4 py-2 font-medium">Lieu</th>
                <th className="px-4 py-2 font-medium">Score</th>
                <th className="px-4 py-2 font-medium">Statut</th>
                <th className="px-4 py-2 font-medium">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {applications.map((application) => (
                <tr key={application.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2">
                    <Link
                      href={`/offre/${application.offer.id}`}
                      className="text-brand hover:underline"
                    >
                      {application.offer.title}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-slate-700">
                    {application.offer.company ?? "—"}
                  </td>
                  <td className="px-4 py-2 text-slate-700">
                    {application.offer.city ?? "—"}
                  </td>
                  <td className="px-4 py-2 text-slate-700">
                    {application.offer.match_score ?? "—"}
                  </td>
                  <td className="px-4 py-2">
                    <span className={`badge ${APPLICATION_STATUS_STYLES[application.status]}`}>
                      {APPLICATION_STATUS_LABELS[application.status]}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-slate-500">
                    {formatDateTime(application.action_at ?? application.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
