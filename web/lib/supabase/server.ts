import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

/**
 * Client Supabase côté serveur, adossé aux cookies de session.
 *
 * Il utilise la clé anonyme : toutes les requêtes passent donc par la RLS, et
 * ne voient que les lignes du compte connecté. La clé `service_role` n'existe
 * que côté service Python.
 */
export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options),
            );
          } catch {
            // Appelé depuis un Server Component : le middleware rafraîchit
            // déjà la session, il n'y a rien à faire ici.
          }
        },
      },
    },
  );
}
