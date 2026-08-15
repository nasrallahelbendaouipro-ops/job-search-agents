import { criteriaSchema } from "@/lib/schemas/criteria";
import { createClient } from "@/lib/supabase/server";

import { CriteriaForm } from "./criteria-form";

export const dynamic = "force-dynamic";

export default async function CriteriaPage() {
  const supabase = await createClient();

  const { data } = await supabase
    .from("profile_criteria")
    .select("version, criteria")
    .eq("is_active", true)
    .maybeSingle();

  if (!data) {
    return (
      <div className="card space-y-2 text-sm">
        <h1 className="text-lg font-semibold text-slate-900">Critères de matching</h1>
        <p className="text-slate-600">
          Aucune version active. Exécute <code>supabase/seed.sql</code> pour
          initialiser les critères, puis recharge cette page.
        </p>
      </div>
    );
  }

  // Le parse remplit les valeurs par défaut si le JSONB stocké précède l'ajout
  // d'un champ au schéma.
  const criteria = criteriaSchema.parse(data.criteria);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Critères de matching</h1>
        <p className="mt-1 text-sm text-slate-600">
          Ces critères pilotent le pré-filtre et le prompt du modèle de filtrage.
          Chaque enregistrement crée une nouvelle version ; l&apos;ancienne est
          conservée.
        </p>
      </header>

      <CriteriaForm initial={criteria} version={data.version} />
    </div>
  );
}
