/** Types des lignes renvoyées par Supabase, alignés sur les migrations. */

export type MatchStatus = "pending" | "matched" | "rejected";

export type ApplyChannel =
  | "email"
  | "form"
  | "easy_apply"
  | "account_required"
  | "unknown";

export type ApplicationStatus =
  | "to_validate"
  | "auto_applied"
  | "manual_required"
  | "sent"
  | "rejected";

export type RunStatus = "running" | "succeeded" | "failed" | "budget_exceeded";

export interface Offer {
  id: string;
  source: string;
  source_offer_id: string;
  country: string;
  title: string;
  company: string | null;
  city: string | null;
  url: string;
  description: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_raw: string | null;
  contract_type: string | null;
  remote_policy: string | null;
  posted_at: string | null;
  scraped_at: string;
  match_status: MatchStatus;
  match_score: number | null;
  match_reason: string | null;
  apply_channel: ApplyChannel;
  apply_email: string | null;
}

export interface Application {
  id: string;
  offer_id: string;
  run_id: string | null;
  status: ApplicationStatus;
  letter_text: string | null;
  letter_storage_path: string | null;
  cv_document_id: string | null;
  created_at: string;
  action_at: string | null;
  error: string | null;
}

export interface ApplicationWithOffer extends Application {
  offer: Offer;
}

export interface AgentRun {
  id: string;
  status: RunStatus;
  started_at: string;
  finished_at: string | null;
  offers_scraped: number;
  offers_matched: number;
  letters_generated: number;
  errors: { stage?: string; source?: string; offer_id?: string; error?: string }[];
}

export interface DocumentRow {
  id: string;
  kind: "cv" | "letter_template";
  label: string;
  language: string;
  storage_path: string;
}

// -- Libellés et couleurs, partagés par toutes les pages --------------------

export const APPLICATION_STATUS_LABELS: Record<ApplicationStatus, string> = {
  to_validate: "À valider",
  auto_applied: "Postulée automatiquement",
  manual_required: "Action manuelle requise",
  sent: "Envoyée",
  rejected: "Écartée",
};

export const APPLICATION_STATUS_STYLES: Record<ApplicationStatus, string> = {
  to_validate: "bg-amber-100 text-amber-800",
  auto_applied: "bg-emerald-100 text-emerald-800",
  manual_required: "bg-sky-100 text-sky-800",
  sent: "bg-emerald-100 text-emerald-800",
  rejected: "bg-slate-200 text-slate-600",
};

export const APPLY_CHANNEL_LABELS: Record<ApplyChannel, string> = {
  email: "Candidature par email",
  form: "Formulaire sans compte",
  easy_apply: "Candidature simplifiée (LinkedIn)",
  account_required: "Création de compte requise",
  unknown: "Canal non identifié",
};

export const RUN_STATUS_LABELS: Record<RunStatus, string> = {
  running: "En cours",
  succeeded: "Terminée",
  failed: "Échec",
  budget_exceeded: "Plafond atteint",
};

export const RUN_STATUS_STYLES: Record<RunStatus, string> = {
  running: "bg-sky-100 text-sky-800",
  succeeded: "bg-emerald-100 text-emerald-800",
  failed: "bg-rose-100 text-rose-800",
  budget_exceeded: "bg-amber-100 text-amber-800",
};

export const CV_LABELS: Record<string, string> = {
  data_analyst: "CV Data Analyst",
  data_scientist: "CV Data Scientist",
  industrial_engineer: "CV Ingénieur industriel",
};

export function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}
