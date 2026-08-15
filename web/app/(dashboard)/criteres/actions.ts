"use server";

import { revalidatePath } from "next/cache";

import { criteriaSchema } from "@/lib/schemas/criteria";
import { createClient } from "@/lib/supabase/server";

/**
 * Enregistre une nouvelle version des critères.
 *
 * Les versions ne sont jamais écrasées : on désactive l'ancienne et on en crée
 * une nouvelle. Si un changement de critères dégrade les résultats, l'historique
 * permet de comprendre ce qui a changé et quand.
 */
export async function saveCriteria(raw: unknown) {
  const parsed = criteriaSchema.safeParse(raw);
  if (!parsed.success) {
    return {
      ok: false as const,
      message: parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join(" · "),
    };
  }

  const supabase = await createClient();

  const { data: user } = await supabase.auth.getUser();
  if (!user.user) return { ok: false as const, message: "Session expirée." };

  const { data: current } = await supabase
    .from("profile_criteria")
    .select("version")
    .order("version", { ascending: false })
    .limit(1)
    .maybeSingle();

  const nextVersion = (current?.version ?? 0) + 1;

  // Désactiver avant d'insérer : l'index unique partiel n'autorise qu'une
  // seule version active à la fois.
  const { error: deactivateError } = await supabase
    .from("profile_criteria")
    .update({ is_active: false })
    .eq("is_active", true);

  if (deactivateError) return { ok: false as const, message: deactivateError.message };

  const { error } = await supabase.from("profile_criteria").insert({
    owner_id: user.user.id,
    version: nextVersion,
    is_active: true,
    criteria: parsed.data,
  });

  if (error) return { ok: false as const, message: error.message };

  revalidatePath("/criteres");
  revalidatePath("/liens");
  return { ok: true as const, version: nextVersion };
}
