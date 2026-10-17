import { useEffect, useState } from "react";
import "./style.css";

type Facet = { value: string | number; count: number };
type Hit = {
  manual_id: string; section_id: string; section_title: string; title: string; snippet: string;
  text: string; category: string; manufacturer: string; year: number; doc_type: string;
  provenance: { manual_id: string; section_id: string; section_title: string; char_offset_start: number; char_offset_end: number; ingest_version: number; source_event_id: string };
};
type Results = { total: number; page: number; hits: Hit[]; facets: Record<string, Facet[]> };

const api = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const pageTitle = "Equipment manual search";

export function SearchApp() {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Results>({ total: 0, page: 1, hits: [], facets: {} });
  const [selected, setSelected] = useState<Hit | null>(null);

  useEffect(() => { void search(); }, []);
  async function search(page = 1) {
    const response = await fetch(`${api}/search?q=${encodeURIComponent(q)}&page=${page}`);
    if (response.ok) setResults(await response.json());
  }
  return <main>
    <header><p className="eyebrow">CQRS / DOCUMENT CATALOG</p><h1>{pageTitle}</h1><p>Search synthetic industrial manuals and trace every match to its source section.</p></header>
    <form onSubmit={(event) => { event.preventDefault(); void search(); }}>
      <input aria-label="Search manuals" value={q} onChange={(event) => setQ(event.target.value)} placeholder="Search safety, alarm, installation..." />
      <button type="submit">Search</button>
    </form>
    <section className="layout">
      <aside><h2>Facets</h2>{Object.entries(results.facets).map(([name, values]) => <div className="facet" key={name}><h3>{name.replace("_", " ")}</h3>{values.map((facet) => <button className="chip" key={String(facet.value)} onClick={() => { setQ(String(facet.value)); void search(); }}>{facet.value} <b>{facet.count}</b></button>)}</div>)}</aside>
      <section className="results"><div className="result-count">{results.total} matching sections</div>{results.hits.map((hit) => <article className="hit" key={hit.section_id} onClick={() => setSelected(hit)}><div className="hit-meta">{hit.category} / {hit.manufacturer} / {hit.year}</div><h2>{hit.title}</h2><p>{hit.snippet}</p><small>{hit.doc_type} · manual {hit.manual_id.slice(0, 8)}</small></article>)}<nav><button disabled={results.page <= 1} onClick={() => void search(results.page - 1)}>Previous</button><button disabled={(results.page * 20) >= results.total} onClick={() => void search(results.page + 1)}>Next</button></nav></section>
      {selected && <aside className="provenance"><button className="close" onClick={() => setSelected(null)}>Close</button><h2>Provenance</h2><dl><dt>Section</dt><dd>{selected.provenance.section_title}</dd><dt>Character range</dt><dd>{selected.provenance.char_offset_start}–{selected.provenance.char_offset_end}</dd><dt>Ingest version</dt><dd>{selected.provenance.ingest_version}</dd><dt>Source event</dt><dd className="mono">{selected.provenance.source_event_id}</dd></dl><pre>{selected.text}</pre></aside>}
    </section>
  </main>;
}
