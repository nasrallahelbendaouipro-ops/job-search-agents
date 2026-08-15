import { createClient } from "@/lib/supabase/server";
import {
  RUN_STATUS_LABELS,
  RUN_STATUS_STYLES,
  formatDateTime,
  type AgentRun,
} from "@/lib/types";

export const dynamic = "force-dynamic";

function monthStartIso(): string {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)).toISOString();
}

export default async function RunsPage() {
  const supabase = await createClient();

  const [{ data: runsData }, { data: usageData }] = await Promise.all([
    supabase
      .from("agent_runs")
      .select("*")
      .order("started_at", { ascending: false })
      .limit(30),
    supabase.from("llm_usage").select("cost_eur, agent").gte("created_at", monthStartIso()),
  ]);

  const runs = (runsData ?? []) as AgentRun[];
  const usage = (usageData ?? []) as { cost_eur: number; agent: string }[];

  const totalSpend = usage.reduce((sum, row) => sum + Number(row.cost_eur), 0);
  const filterSpend = usage
    .filter((row) => row.agent === "filter")
    .reduce((sum, row) => sum + Number(row.cost_eur), 0);
  const writerSpend = totalSpend - filterSpend;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Exécutions</h1>
        <p className="mt-1 text-sm text-slate-600">
          Le pipeline tourne chaque nuit à 3 h (Europe/Paris).
        </p>
      </header>

      <section className="grid gap-3 sm:grid-cols-3">
        <div className="card">
          <p className="text-xs uppercase tracking-wide text-slate-500">
            Dépense LLM ce mois
          </p>
          <p className="mt-1 text-2xl font-semibold text-brand">
            {totalSpend.toFixed(2)} €
          </p>
        </div>
        <div className="card">
          <p className="text-xs uppercase tracking-wide text-slate-500">Filtrage</p>
          <p className="mt-1 text-2xl font-semibold text-slate-800">
            {filterSpend.toFixed(2)} €
          </p>
        </div>
        <div className="card">
          <p className="text-xs uppercase tracking-wide text-slate-500">Rédaction</p>
          <p className="mt-1 text-2xl font-semibold text-slate-800">
            {writerSpend.toFixed(2)} €
          </p>
        </div>
      </section>

      {runs.length === 0 ? (
        <p className="card text-sm text-slate-600">
          Aucune exécution enregistrée pour l&apos;instant.
        </p>
      ) : (
        <div className="space-y-3">
          {runs.map((run) => (
            <article key={run.id} className="card space-y-2">
              <div className="flex flex-wrap items-center gap-3">
                <span className={`badge ${RUN_STATUS_STYLES[run.status]}`}>
                  {RUN_STATUS_LABELS[run.status]}
                </span>
                <span className="text-sm text-slate-700">
                  {formatDateTime(run.started_at)}
                </span>
                <div className="flex-1" />
                <span className="text-sm text-slate-600">
                  {run.offers_scraped} récupérées · {run.offers_matched} retenues ·{" "}
                  {run.letters_generated} lettres
                </span>
              </div>

              {run.status === "budget_exceeded" && (
                <p className="rounded-md bg-amber-50 p-2 text-sm text-amber-800">
                  Le plafond mensuel a été atteint : l&apos;exécution s&apos;est
                  arrêtée avant de dépenser davantage. Relève{" "}
                  <code>MONTHLY_BUDGET_EUR</code> si c&apos;est volontaire.
                </p>
              )}

              {run.errors?.length > 0 && (
                <details className="text-sm">
                  <summary className="cursor-pointer text-rose-700">
                    {run.errors.length} erreur{run.errors.length > 1 ? "s" : ""}
                  </summary>
                  <ul className="mt-2 space-y-1 text-slate-600">
                    {run.errors.map((err, index) => (
                      <li key={index} className="font-mono text-xs">
                        [{err.stage ?? "?"}] {err.source ?? err.offer_id ?? ""} {err.error}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
