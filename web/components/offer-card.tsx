import Link from "next/link";

import {
  APPLICATION_STATUS_LABELS,
  APPLICATION_STATUS_STYLES,
  APPLY_CHANNEL_LABELS,
  formatDateTime,
  type ApplicationWithOffer,
} from "@/lib/types";

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return null;

  const tone =
    score >= 85
      ? "bg-emerald-100 text-emerald-800"
      : score >= 65
        ? "bg-sky-100 text-sky-800"
        : "bg-slate-200 text-slate-700";

  return <span className={`badge ${tone}`}>{score}/100</span>;
}

export function OfferCard({ application }: { application: ApplicationWithOffer }) {
  const { offer } = application;

  return (
    <article className="card space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate font-semibold text-slate-900">{offer.title}</h3>
          <p className="truncate text-sm text-slate-600">
            {offer.company ?? "Entreprise non précisée"}
            {offer.city ? ` · ${offer.city}` : ""}
            {offer.contract_type ? ` · ${offer.contract_type}` : ""}
          </p>
        </div>
        <ScoreBadge score={offer.match_score} />
      </div>

      {offer.match_reason && (
        <p className="rounded-md bg-slate-50 p-2 text-sm text-slate-700">
          {offer.match_reason}
        </p>
      )}

      <dl className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
        {offer.salary_raw && (
          <div>
            <dt className="inline">Salaire : </dt>
            <dd className="inline">{offer.salary_raw}</dd>
          </div>
        )}
        <div>
          <dt className="inline">Canal : </dt>
          <dd className="inline">{APPLY_CHANNEL_LABELS[offer.apply_channel]}</dd>
        </div>
        <div>
          <dt className="inline">Trouvée le : </dt>
          <dd className="inline">{formatDateTime(offer.scraped_at)}</dd>
        </div>
      </dl>

      <div className="flex items-center gap-2 pt-1">
        <span className={`badge ${APPLICATION_STATUS_STYLES[application.status]}`}>
          {APPLICATION_STATUS_LABELS[application.status]}
        </span>
        <div className="flex-1" />
        <a
          href={offer.url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-secondary"
        >
          Voir l&apos;annonce
        </a>
        <Link href={`/offre/${offer.id}`} className="btn-primary">
          Ouvrir la lettre
        </Link>
      </div>
    </article>
  );
}
