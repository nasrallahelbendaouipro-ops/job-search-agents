"use server";

import { revalidatePath } from "next/cache";

import { createClient } from "@/lib/supabase/server";

/**
 * Actions déclenchées depuis la page d'une offre.
 *
 * Aucune de ces actions n'envoie de candidature : marquer « envoyée » suppose
 * que tu as fait l'envoi toi-même. L'envoi automatisé n'existe pas encore —
 * le pipeline nocturne prépare, tu décides.
 */

export async function saveLetter(applicationId: string, letterText: string) {
  const supabase = await createClient();

  const { error } = await supabase
    .from("applications")
    .update({ letter_text: letterText })
    .eq("id", applicationId);

  if (error) return { ok: false as const, message: error.message };

  revalidatePath("/");
  return { ok: true as const };
}

export async function markAsSent(applicationId: string, offerId: string) {
  const supabase = await createClient();

  const { error } = await supabase
    .from("applications")
    .update({ status: "sent", action_at: new Date().toISOString() })
    .eq("id", applicationId);

  if (error) return { ok: false as const, message: error.message };

  revalidatePath("/");
  revalidatePath(`/offre/${offerId}`);
  revalidatePath("/historique");
  return { ok: true as const };
}

export async function rejectOffer(applicationId: string, offerId: string) {
  const supabase = await createClient();

  const { error } = await supabase
    .from("applications")
    .update({ status: "rejected", action_at: new Date().toISOString() })
    .eq("id", applicationId);

  if (error) return { ok: false as const, message: error.message };

  revalidatePath("/");
  revalidatePath(`/offre/${offerId}`);
  return { ok: true as const };
}

/**
 * URL signée pour télécharger la lettre .docx.
 *
 * Les buckets sont privés : on ne peut pas lier directement le fichier, il
 * faut une URL temporaire.
 */
export async function letterDownloadUrl(storagePath: string) {
  const supabase = await createClient();

  const { data, error } = await supabase.storage
    .from("letters")
    .createSignedUrl(storagePath, 300);

  if (error || !data) return { ok: false as const, message: error?.message ?? "" };
  return { ok: true as const, url: data.signedUrl };
}
