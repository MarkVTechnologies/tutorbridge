import { Loader2, MapPin } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { api } from "@/lib/api";
import { cn } from "@/lib/cn";

export type Place = { label: string; lat: number; lng: number; area_id: number | null; area_name: string | null };

/**
 * Address autocomplete backed by the server's cached geocoder (OpenStreetMap or Google).
 * Typing still works if search is unavailable — the address is kept as free text.
 */
export function AddressSearch({ label, value, onChange, onPick, hint, error }: {
  label: string; value: string; onChange: (v: string) => void; onPick: (p: Place) => void; hint?: string; error?: string;
}) {
  const id = useId();
  const [results, setResults] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [busy, setBusy] = useState(false);
  const [noMatch, setNoMatch] = useState(false);
  const picked = useRef(false);

  useEffect(() => {
    if (picked.current) { picked.current = false; return; }
    const q = value.trim();
    setNoMatch(false);
    if (q.length < 4) { setResults([]); return; }
    const t = setTimeout(async () => {
      setBusy(true);
      try {
        const r = await api.get<Place[]>(`/geo/search/?q=${encodeURIComponent(q)}`);
        setResults(r);
        setNoMatch(r.length === 0);
        setOpen(true);
        setActive(-1);
      } catch {
        setResults([]);
        setNoMatch(true);
      } finally {
        setBusy(false);
      }
    }, 600); // debounce: OpenStreetMap allows ~1 request/second
    return () => clearTimeout(t);
  }, [value]);

  const choose = (p: Place) => {
    picked.current = true;
    onChange(p.label);
    onPick(p);
    setOpen(false);
  };

  return (
    <div className="relative space-y-1.5">
      <label htmlFor={id} className="block text-[13px] font-semibold text-ink-700">{label}</label>
      <div className="relative">
        <MapPin className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-ink-400" />
        <input id={id} role="combobox" aria-expanded={open && results.length > 0} aria-controls={`${id}-list`} aria-autocomplete="list" autoComplete="off"
          aria-activedescendant={active >= 0 ? `${id}-opt-${active}` : undefined} aria-invalid={!!error}
          className="input pr-10 pl-10" value={value} placeholder="Start typing your street and area…"
          onChange={(e) => onChange(e.target.value)} onFocus={() => results.length && setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (!open || !results.length) return;
            if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
            else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
            else if (e.key === "Enter" && active >= 0) { e.preventDefault(); choose(results[active]); }
            else if (e.key === "Escape") setOpen(false);
          }} />
        {busy && <Loader2 className="absolute top-1/2 right-3.5 size-4 -translate-y-1/2 animate-spin text-ink-400" />}
      </div>
      {open && results.length > 0 && (
        <ul id={`${id}-list`} role="listbox" className="absolute z-20 mt-1 w-full overflow-hidden rounded-2xl border border-ink-100 bg-white py-1 shadow-lift">
          {results.map((r, i) => (
            <li key={`${r.lat},${r.lng},${i}`} id={`${id}-opt-${i}`} role="option" aria-selected={i === active}
              onMouseDown={(e) => { e.preventDefault(); choose(r); }} onMouseEnter={() => setActive(i)}
              className={cn("flex cursor-pointer items-start gap-2.5 px-3.5 py-2.5 text-sm", i === active ? "bg-brand-50" : "hover:bg-ink-50")}>
              <MapPin className="mt-0.5 size-4 shrink-0 text-brand-500" />
              <span className="min-w-0"><span className="block truncate text-ink-800">{r.label}</span>
                {r.area_name && <span className="text-xs text-ink-500">Near {r.area_name}</span>}</span>
            </li>
          ))}
        </ul>
      )}
      {noMatch && !error && <p className="text-xs text-ink-500">No suggestions found — that's fine, just type your full address (street, area).</p>}
      {hint && !error && !noMatch && <p className="text-xs leading-relaxed text-ink-500">{hint}</p>}
      {error && <p className="text-[13px] text-red-600">{error}</p>}
    </div>
  );
}
