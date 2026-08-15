import Link from "next/link";
import { notFound } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import {
  APPLICATION_STATUS_LABELS,
  APPLICATION_STATUS_STYLES,
  APPLY_CHANNEL_LABELS,
  CV_LABELS,
  formatDateTime,
  type Application,
  type DocumentRow,
  type Offer,
} from "@/lib/types";

import { LetterEditor } from "./letter-editor";

export const dynamic = "force-dynamic";

/** Ce qu'il te reste à faire, selon le canal détecté par l'agent. */
const CHANNEL_NOTES: Record<Offer["apply_channel"], string> = {
  email: "Candidature par email : joins le CV et la lettre, puis envoie depuis ta messagerie.",
  form: "Formulaire sans création de compte : ouvre l'annonce et dépose les documents.",
  easy_apply:
    "Candidature simplifiée LinkedIn. Elle reste manuelle volontairement : l'automatiser violerait les CGU et exposerait ton compte à une suspension.",
  account_required:
    "Création de compte ou parcours multi-étapes requis : ouvre l'annonce et suis le processus.",
  unknown: "Canal non identifié : ouvre l'annonce pour voir comment postuler.",
};

export default async function OfferPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();

  const [{ data: offerRow }, { data: applicationRow }] = await Promise.all([
    supabase.from("offers").select("*").eq("id", id).maybeSingle(),
    supabase.from("applications").select("*").eq("offer_id", id).maybeSingle(),
  ]);

  if (!offerRow) notFound();

  const offer = offerRow as Offer;
  const application = applicationRow as Application | null;

  let cv: DocumentRow | null = null;
  if (application?.cv_document_id) {
    const { data } = await supabase
      .from("documents")
      .select("*")
      .eq("id", application.cv_document_id)
      .maybeSingle();
    cv = (data as DocumentRow) ?? null;
  }

  return (
    <div className="space-y-6">
      <Link href="/" className="text-sm text-brand hover:underline">
        ← Retour aux offres du jour
      </Link>

      <header className="card space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-slate-900">{offer.title}</h1>
            <p className="text-sm text-slate-600">
              {offer.company ?? "Entreprise non précisée"}
              {offer.city ? ` · ${offer.city}` : ""} · {offer.country}
            </p>
          </div>
          {application && (
            <span className={`badge ${APPLICATION_STATUS_STYLES[application.status]}`}>
              {APPLICATION_STATUS_LABELS[application.status]}
            </span>
          )}
        </div>

        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="inline text-slate-500">Score : </dt>
            <dd className="inline font-medium">{offer.match_score ?? "—"}/100</dd>
          </div>
          <div>
            <dt className="inline text-slate-500">Contrat : </dt>
            <dd className="inline">{offer.contract_type ?? "non précisé"}</dd>
          </div>
          <div>
            <dt className="inline text-slate-500">Salaire : </dt>
            <dd className="inline">{offer.salary_raw ?? "non affiché"}</dd>
          </div>
          <div>
            <dt className="inline text-slate-500">Télétravail : </dt>
            <dd className="inline">{offer.remote_policy ?? "non précisé"}</dd>
          </div>
          <div>
            <dt className="inline text-slate-500">Canal : </dt>
            <dd className="inline">{APPLY_CHANNEL_LABELS[offer.apply_channel]}</dd>
          </div>
          <div>
            <dt className="inline text-slate-500">CV retenu : </dt>
            <dd className="inline">{cv ? (CV_LABELS[cv.label] ?? cv.label) : "aucun"}</dd>
          </div>
          <div>
            <dt className="inline text-slate-500">Publiée le : </dt>
            <dd className="inline">{formatDateTime(offer.posted_at)}</dd>
          </div>
          <div>
            <dt className="inline text-slate-500">Source : </dt>
            <dd className="inline">{offer.source}</dd>
          </div>
        </dl>

        {offer.match_reason && (
          <p className="rounded-md bg-slate-50 p-3 text-sm text-slate-700">
            <span className="font-medium">Raison du match : </span>
            {offer.match_reason}
          </p>
        )}
      </header>

      {application ? (
        <LetterEditor
          applicationId={application.id}
          offerId={offer.id}
          initialText={application.letter_text ?? ""}
          storagePath={application.letter_storage_path}
          applyEmail={offer.apply_email}
          status={application.status}
          channelNote={CHANNEL_NOTES[offer.apply_channel]}
          offerUrl={offer.url}
        />
      ) : (
        <p className="card text-sm text-slate-600">
          Aucune lettre n&apos;a été générée pour cette offre — elle a été écartée
          au filtrage, ou le plafond de lettres par nuit était atteint.
        </p>
      )}

      <section className="card">
        <h2 className="mb-2 font-semibold text-slate-900">Description de l&apos;offre</h2>
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
          {offer.description ?? "Aucune description fournie par la source."}
        </p>
      </section>
    </div>
  );
}
