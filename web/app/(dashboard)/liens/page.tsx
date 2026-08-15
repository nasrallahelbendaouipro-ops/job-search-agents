import { criteriaSchema, COUNTRY_LABELS, type Criteria } from "@/lib/schemas/criteria";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

/**
 * LinkedIn et Indeed interdisent le scraping dans leurs conditions
 * d'utilisation. Plutôt que de construire un scraper qui exposerait le compte
 * à une suspension, cette page génère les liens de recherche correspondant aux
 * critères actifs — à ouvrir manuellement.
 */

const LINKEDIN_GEO: Record<string, string> = {
  FR: "105015875", // France
  MA: "102787409", // Maroc
  DE: "101282230", // Allemagne
};

const INDEED_DOMAIN: Record<string, string> = {
  FR: "fr.indeed.com",
  MA: "ma.indeed.com",
  DE: "de.indeed.com",
};

interface SearchLink {
  site: "LinkedIn" | "Indeed";
  country: string;
  keyword: string;
  city: string | null;
  url: string;
}

function buildLinks(criteria: Criteria): SearchLink[] {
  const links: SearchLink[] = [];
  // Les trois premiers intitulés suffisent : au-delà, la page devient une
  // liste illisible de dizaines de liens quasi identiques.
  const keywords = criteria.titles_include.slice(0, 3);

  for (const country of [...criteria.countries].sort((a, b) => a.priority - b.priority)) {
    const targets = country.cities.length > 0 ? country.cities : [null];

    for (const keyword of keywords) {
      for (const city of targets) {
        const geoId = LINKEDIN_GEO[country.code];
        if (geoId) {
          const params = new URLSearchParams({ keywords: keyword, f_TPR: "r86400" });
          if (city) params.set("location", city);
          else params.set("geoId", geoId);
          links.push({
            site: "LinkedIn",
            country: country.code,
            keyword,
            city,
            url: `https://www.linkedin.com/jobs/search/?${params}`,
          });
        }

        const domain = INDEED_DOMAIN[country.code];
        if (domain) {
          const params = new URLSearchParams({ q: keyword, fromage: "1" });
          if (city) params.set("l", city);
          links.push({
            site: "Indeed",
            country: country.code,
            keyword,
            city,
            url: `https://${domain}/jobs?${params}`,
          });
        }
      }
    }
  }

  return links;
}

export default async function ManualLinksPage() {
  const supabase = await createClient();

  const { data } = await supabase
    .from("profile_criteria")
    .select("criteria")
    .eq("is_active", true)
    .maybeSingle();

  if (!data) {
    return (
      <p className="card text-sm text-slate-600">
        Aucun critère actif : exécute <code>supabase/seed.sql</code>, puis reviens
        ici.
      </p>
    );
  }

  const criteria = criteriaSchema.parse(data.criteria);
  const links = buildLinks(criteria);
  const byCountry = new Map<string, SearchLink[]>();
  for (const link of links) {
    byCountry.set(link.country, [...(byCountry.get(link.country) ?? []), link]);
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Liens manuels</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          LinkedIn et Indeed interdisent le scraping dans leurs conditions
          d&apos;utilisation. Aucun agent ne les parcourt : ces recherches sont
          pré-remplies à partir de tes critères actifs, filtrées sur les
          dernières 24 h. Ouvre-les toi-même — c&apos;est plus lent, mais ton
          compte ne risque rien.
        </p>
      </header>

      {[...byCountry.entries()].map(([code, countryLinks]) => (
        <section key={code} className="card space-y-3">
          <h2 className="font-semibold text-slate-900">
            {COUNTRY_LABELS[code] ?? code}
          </h2>
          <ul className="space-y-2">
            {countryLinks.map((link) => (
              <li key={link.url} className="flex flex-wrap items-center gap-2 text-sm">
                <span
                  className={`badge ${
                    link.site === "LinkedIn"
                      ? "bg-sky-100 text-sky-800"
                      : "bg-indigo-100 text-indigo-800"
                  }`}
                >
                  {link.site}
                </span>
                <span className="text-slate-700">{link.keyword}</span>
                {link.city && <span className="text-slate-500">· {link.city}</span>}
                <div className="flex-1" />
                <a
                  href={link.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-brand hover:underline"
                >
                  Ouvrir la recherche →
                </a>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
