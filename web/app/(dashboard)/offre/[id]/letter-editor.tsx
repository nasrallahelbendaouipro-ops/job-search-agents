"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  letterDownloadUrl,
  markAsSent,
  rejectOffer,
  saveLetter,
} from "./actions";

interface Props {
  applicationId: string;
  offerId: string;
  initialText: string;
  storagePath: string | null;
  applyEmail: string | null;
  status: string;
  channelNote: string;
  offerUrl: string;
}

export function LetterEditor({
  applicationId,
  offerId,
  initialText,
  storagePath,
  applyEmail,
  status,
  channelNote,
  offerUrl,
}: Props) {
  const router = useRouter();
  const [text, setText] = useState(initialText);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const isClosed = status === "sent" || status === "rejected";
  const dirty = text !== initialText;

  function run(action: () => Promise<{ ok: boolean; message?: string }>, success: string) {
    setMessage(null);
    startTransition(async () => {
      const result = await action();
      if (result.ok) {
        setMessage(success);
        router.refresh();
      } else {
        setMessage(result.message ?? "Une erreur est survenue.");
      }
    });
  }

  async function download() {
    if (!storagePath) return;
    const result = await letterDownloadUrl(storagePath);
    if (result.ok) {
      window.open(result.url, "_blank", "noopener");
    } else {
      setMessage("Téléchargement impossible : " + result.message);
    }
  }

  return (
    <section className="card space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-semibold text-slate-900">Lettre de motivation</h2>
        {dirty && <span className="text-xs text-amber-600">Modifications non enregistrées</span>}
      </div>

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={20}
        disabled={isClosed}
        className="input font-mono text-sm leading-relaxed"
        aria-label="Texte de la lettre"
      />

      <p className="text-xs text-slate-500">
        Le .docx déjà généré conserve la mise en forme d&apos;origine. Si tu modifies
        le texte ici, télécharge-le pour vérifier, ou copie ce texte dans ton
        propre document.
      </p>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-secondary"
          disabled={pending || isClosed || !dirty}
          onClick={() => run(() => saveLetter(applicationId, text), "Lettre enregistrée.")}
        >
          Enregistrer les modifications
        </button>

        {storagePath && (
          <button type="button" className="btn-secondary" onClick={download}>
            Télécharger le .docx
          </button>
        )}
      </div>

      <hr className="border-slate-200" />

      <div className="space-y-3">
        <p className="text-sm text-slate-600">{channelNote}</p>

        {applyEmail && (
          <p className="text-sm">
            Adresse de candidature :{" "}
            <a href={`mailto:${applyEmail}`} className="text-brand underline">
              {applyEmail}
            </a>
          </p>
        )}

        <div className="flex flex-wrap gap-2">
          <a href={offerUrl} target="_blank" rel="noopener noreferrer" className="btn-secondary">
            Ouvrir l&apos;annonce
          </a>

          <button
            type="button"
            className="btn-primary"
            disabled={pending || isClosed}
            onClick={() =>
              run(() => markAsSent(applicationId, offerId), "Marquée comme envoyée.")
            }
          >
            {status === "sent" ? "Déjà envoyée ✅" : "J'ai envoyé cette candidature"}
          </button>

          <button
            type="button"
            className="btn-ghost text-rose-600 hover:bg-rose-50"
            disabled={pending || isClosed}
            onClick={() => run(() => rejectOffer(applicationId, offerId), "Offre écartée.")}
          >
            Écarter
          </button>
        </div>

        <p className="text-xs text-slate-500">
          Le bouton d&apos;envoi enregistre ta décision : il ne transmet rien
          lui-même. L&apos;envoi automatique n&apos;est pas actif.
        </p>
      </div>

      {message && <p className="text-sm text-slate-700">{message}</p>}
    </section>
  );
}
