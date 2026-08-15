import { OfferCard } from "@/components/offer-card";
import { createClient } from "@/lib/supabase/server";
import { formatDate, type ApplicationWithOffer } from "@/lib/types";

export const dynamic = "force-dynamic";

/** Candidatures ouvertes, groupées par ce que tu dois en faire. */
const GROUPS = [
  {
    status: "to_validate" as const,
    title: "À valider",
    hint: "Lettre prête. Relis-la, puis envoie.",
  },
  {
    status: "manual_required" as const,
    title: "Action manuelle requise",
    hint: "Compte à créer ou candidature simplifiée : ouvre le lien et joins les documents.",
  },
];

export default async function TodayPage() {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("applications")
    .select("*, offer:offers(*)")
    .in("status", ["to_validate", "manual_required"])
    .order("created_at", { ascending: false });

  if (error) {
    return (
      <p className="card text-sm text-rose-600">
        Impossible de charger les candidatures : {error.message}
      </p>
    );
  }

  const applications = (data ?? []) as unknown as ApplicationWithOffer[];

  // Les meilleurs scores en premier à l'intérieur de chaque groupe.
  applications.sort((a, b) => (b.offer.match_score ?? 0) - (a.offer.match_score ?? 0));

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">
          {formatDate(new Date().toISOString())}
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          {applications.length === 0
            ? "Rien à traiter pour le moment."
            : `${applications.length} candidature${applications.length > 1 ? "s" : ""} en attente.`}
        </p>
      </header>

      {applications.length === 0 && (
        <div className="card text-sm text-slate-600">
          <p>
            Aucune offre en attente. Le pipeline tourne chaque nuit à 3 h — reviens
            demain matin, ou consulte{" "}
            <a href="/runs" className="text-brand underline">
              les dernières exécutions
            </a>{" "}
            pour vérifier qu&apos;il s&apos;est bien déroulé.
          </p>
        </div>
      )}

      {GROUPS.map((group) => {
        const items = applications.filter((a) => a.status === group.status);
        if (items.length === 0) return null;

        return (
          <section key={group.status} className="space-y-3">
            <div>
              <h2 className="text-lg font-medium text-slate-900">
                {group.title}{" "}
                <span className="text-sm font-normal text-slate-500">({items.length})</span>
              </h2>
              <p className="text-sm text-slate-500">{group.hint}</p>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {items.map((application) => (
                <OfferCard key={application.id} application={application} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
