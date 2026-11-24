import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type Catalog } from "./api";

const CatalogContext = createContext<Catalog | null>(null);

/** Loads the system-scope catalog once and shares it with every page. */
export function CatalogProvider({ children }: { children: ReactNode }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.catalog().then(setCatalog).catch((e: Error) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="page">
        <div className="alert error">
          Cannot reach the API ({error}). Start it with <code>uvicorn app.api.main:app --reload</code>.
        </div>
      </div>
    );
  }
  if (!catalog) return <div className="page muted">Loading…</div>;
  return <CatalogContext.Provider value={catalog}>{children}</CatalogContext.Provider>;
}

export function useCatalog() {
  const catalog = useContext(CatalogContext);
  if (!catalog) throw new Error("useCatalog must be used inside CatalogProvider");
  const byId = <T extends { id: string }>(list: T[]) => Object.fromEntries(list.map((x) => [x.id, x]));
  return {
    ...catalog,
    role: byId(catalog.roles),
    domain: byId(catalog.domains),
    source: byId(catalog.sources),
    category: byId(catalog.categories),
  };
}
