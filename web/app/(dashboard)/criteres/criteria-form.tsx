"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  COUNTRY_LABELS,
  REMOTE_LABELS,
  arrayToLines,
  linesToArray,
  type Criteria,
} from "@/lib/schemas/criteria";

import { saveCriteria } from "./actions";

function ListField({
  label,
  hint,
  value,
  onChange,
  rows = 6,
}: {
  label: string;
  hint?: string;
  value: string[];
  onChange: (next: string[]) => void;
  rows?: number;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      {hint && <p className="mb-1 text-xs text-slate-500">{hint}</p>}
      <textarea
        className="input font-mono text-sm"
        rows={rows}
        value={arrayToLines(value)}
        onChange={(e) => onChange(linesToArray(e.target.value))}
      />
    </div>
  );
}

export function CriteriaForm({
  initial,
  version,
}: {
  initial: Criteria;
  version: number | null;
}) {
  const router = useRouter();
  const [criteria, setCriteria] = useState<Criteria>(initial);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function patch(changes: Partial<Criteria>) {
    setCriteria((prev) => ({ ...prev, ...changes }));
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setMessage(null);
    startTransition(async () => {
      const result = await saveCriteria(criteria);
      setMessage(
        result.ok
          ? `Enregistré — version ${result.version}. La prochaine exécution en tiendra compte.`
          : `Erreur : ${result.message}`,
      );
      if (result.ok) router.refresh();
    });
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      <div className="card space-y-4">
        <h2 className="font-semibold text-slate-900">Intitulés de poste</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <ListField
            label="Intitulés recherchés"
            hint="Un par ligne. Une offre doit contenir l'un d'eux pour être examinée."
            value={criteria.titles_include}
            onChange={(v) => patch({ titles_include: v })}
          />
          <ListField
            label="Intitulés à exclure"
            hint="Écarte l'offre si le terme apparaît dans le titre (stage, alternance…)."
            value={criteria.titles_exclude}
            onChange={(v) => patch({ titles_exclude: v })}
          />
        </div>
      </div>

      <div className="card space-y-4">
        <h2 className="font-semibold text-slate-900">Mots-clés</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <ListField
            label="Compétences valorisées"
            hint="Augmentent le score sans être obligatoires."
            value={criteria.keywords_bonus}
            onChange={(v) => patch({ keywords_bonus: v })}
          />
          <ListField
            label="À proscrire"
            hint="Écarte l'offre si le terme apparaît dans le titre ou la description."
            value={criteria.keywords_exclude}
            onChange={(v) => patch({ keywords_exclude: v })}
          />
        </div>
      </div>

      <div className="card space-y-4">
        <h2 className="font-semibold text-slate-900">Pays et villes</h2>
        <p className="text-xs text-slate-500">
          Priorité 1 = la plus haute. Laisse les villes vides pour couvrir tout le pays.
        </p>

        {criteria.countries.map((country, index) => (
          <div key={country.code} className="grid gap-3 border-t border-slate-100 pt-3 md:grid-cols-4">
            <div className="font-medium text-slate-700">
              {COUNTRY_LABELS[country.code] ?? country.code}
            </div>

            <div>
              <label className="label">Priorité</label>
              <input
                type="number"
                min={1}
                max={5}
                className="input"
                value={country.priority}
                onChange={(e) => {
                  const next = [...criteria.countries];
                  next[index] = { ...country, priority: Number(e.target.value) };
                  patch({ countries: next });
                }}
              />
            </div>

            <div>
              <label className="label">Salaire annuel minimum</label>
              <input
                type="number"
                min={0}
                step={1000}
                className="input"
                value={criteria.salary_min_by_country[country.code] ?? 0}
                onChange={(e) =>
                  patch({
                    salary_min_by_country: {
                      ...criteria.salary_min_by_country,
                      [country.code]: Number(e.target.value),
                    },
                  })
                }
              />
            </div>

            <div>
              <label className="label">Villes (une par ligne)</label>
              <textarea
                className="input font-mono text-sm"
                rows={3}
                value={arrayToLines(country.cities)}
                onChange={(e) => {
                  const next = [...criteria.countries];
                  next[index] = { ...country, cities: linesToArray(e.target.value) };
                  patch({ countries: next });
                }}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="card space-y-4">
        <h2 className="font-semibold text-slate-900">Préférences</h2>
        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <label className="label">Télétravail</label>
            <select
              className="input"
              value={criteria.remote_preference}
              onChange={(e) =>
                patch({ remote_preference: e.target.value as Criteria["remote_preference"] })
              }
            >
              {Object.entries(REMOTE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="label">Score minimum pour retenir une offre</label>
            <input
              type="number"
              min={0}
              max={100}
              className="input"
              value={criteria.min_score_to_keep}
              onChange={(e) => patch({ min_score_to_keep: Number(e.target.value) })}
            />
            <p className="mt-1 text-xs text-slate-500">
              Plus haut = moins d&apos;offres retenues, moins de lettres générées,
              moins de dépense.
            </p>
          </div>

          <ListField
            label="Types de contrat"
            value={criteria.contract_types}
            onChange={(v) => patch({ contract_types: v })}
            rows={3}
          />
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <ListField
            label="Secteurs visés"
            value={criteria.sectors}
            onChange={(v) => patch({ sectors: v })}
            rows={3}
          />
          <ListField
            label="Langues maîtrisées"
            hint="Codes courts : fr, en, de…"
            value={criteria.languages_ok}
            onChange={(v) => patch({ languages_ok: v })}
            rows={3}
          />
        </div>
      </div>

      <div className="card space-y-3">
        <h2 className="font-semibold text-slate-900">Auto-envoi</h2>
        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            className="mt-1"
            checked={criteria.auto_send_enabled}
            onChange={(e) => patch({ auto_send_enabled: e.target.checked })}
          />
          <span className="text-sm text-slate-700">
            Activer l&apos;auto-envoi pour les candidatures par email
            <span className="mt-1 block text-xs text-slate-500">
              À laisser désactivé tant que tu n&apos;as pas vérifié la qualité des
              lettres sur plusieurs semaines. Même activé, le pipeline nocturne ne
              soumet rien : la case change seulement le libellé du bouton de
              validation dans le dashboard.
            </span>
          </span>
        </label>
      </div>

      <div className="flex items-center gap-3">
        <button type="submit" className="btn-primary" disabled={pending}>
          {pending ? "Enregistrement…" : "Enregistrer une nouvelle version"}
        </button>
        {version !== null && (
          <span className="text-sm text-slate-500">Version active : {version}</span>
        )}
      </div>

      {message && <p className="text-sm text-slate-700">{message}</p>}
    </form>
  );
}
