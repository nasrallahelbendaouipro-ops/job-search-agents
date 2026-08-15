import { z } from "zod";

/**
 * Schéma des critères de matching, stockés dans `profile_criteria.criteria`.
 *
 * C'est la source de vérité du format JSONB : le miroir Python est
 * `agents/models.py::Criteria`. Toute modification ici doit être répercutée
 * là-bas (le test `test_seed_loads_into_criteria_model` échouera sinon).
 */

export const countryTargetSchema = z.object({
  code: z.string().length(2).toUpperCase(),
  priority: z.number().int().min(1).max(5).default(1),
  /** Liste vide = tout le pays. */
  cities: z.array(z.string().min(1)).default([]),
});

export const criteriaSchema = z.object({
  titles_include: z.array(z.string().min(1)).default([]),
  titles_exclude: z.array(z.string().min(1)).default([]),
  keywords_bonus: z.array(z.string().min(1)).default([]),
  keywords_exclude: z.array(z.string().min(1)).default([]),
  countries: z.array(countryTargetSchema).default([]),
  languages_ok: z.array(z.string().min(2)).default(["fr", "en"]),
  /** Salaire annuel brut minimum, par code pays, en devise locale. */
  salary_min_by_country: z.record(z.string().length(2), z.number().nonnegative()).default({}),
  remote_preference: z
    .enum(["any", "prefer_remote", "prefer_hybrid", "prefer_onsite"])
    .default("any"),
  contract_types: z.array(z.string().min(1)).default(["CDI"]),
  sectors: z.array(z.string().min(1)).default([]),
  min_score_to_keep: z.number().int().min(0).max(100).default(65),
  /**
   * Interrupteur d'auto-envoi. Reste à false tant que la qualité des lettres
   * n'a pas été vérifiée sur plusieurs semaines. Même à true, le pipeline
   * nocturne ne soumet rien : seul le dashboard peut déclencher un envoi.
   */
  auto_send_enabled: z.boolean().default(false),
});

export type Criteria = z.infer<typeof criteriaSchema>;
export type CountryTarget = z.infer<typeof countryTargetSchema>;

export const REMOTE_LABELS: Record<Criteria["remote_preference"], string> = {
  any: "Indifférent",
  prefer_remote: "Télétravail privilégié",
  prefer_hybrid: "Hybride privilégié",
  prefer_onsite: "Présentiel privilégié",
};

export const COUNTRY_LABELS: Record<string, string> = {
  FR: "France",
  MA: "Maroc",
  DE: "Allemagne",
};

/**
 * Convertit une saisie « un élément par ligne » en tableau nettoyé.
 * Les formulaires du dashboard utilisent des textarea plutôt que des listes
 * de champs : plus rapide à éditer pour une liste de vingt mots-clés.
 */
export function linesToArray(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function arrayToLines(value: string[]): string {
  return value.join("\n");
}
