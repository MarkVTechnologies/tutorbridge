import { useState } from "react";

import { Pagination } from "@/components/ui";
import { qs, type Paginated } from "@/lib/api";
import { useApi } from "@/lib/hooks";

/** Paginated staff list with filters kept in component state. */
export function usePaged<T>(base: string, filters: Record<string, string | undefined> = {}) {
  const [page, setPage] = useState(1);
  const path = `${base}${qs({ ...filters, page })}`;
  const q = useApi<Paginated<T>>(path, [base, filters, page]);
  const pager = q.data ? <Pagination page={page} count={q.data.count} onPage={setPage} /> : null;
  return { ...q, rows: q.data?.results ?? [], pager, setPage };
}

export function Json({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="text-slate-400">—</span>;
  return <pre className="max-h-48 overflow-auto rounded bg-slate-50 p-2 text-xs whitespace-pre-wrap">{JSON.stringify(value, null, 2)}</pre>;
}
