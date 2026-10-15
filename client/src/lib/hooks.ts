import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "react-toastify";

import { api, ApiError } from "./api";
import type { RefData } from "./types";

export function useRefData() {
  return useQuery({ queryKey: ["ref"], queryFn: () => api.get<RefData>("/ref/"), staleTime: 10 * 60_000 });
}

export function useApi<T>(path: string | null, key?: QueryKey) {
  return useQuery({ queryKey: key ?? [path], queryFn: () => api.get<T>(path!), enabled: !!path });
}

/**
 * Mutation helper: invalidates the given query keys on success, exposes a friendly
 * error for inline display, and optionally confirms success with a toast.
 */
export function useAction<TArgs = void, TResult = unknown>(
  fn: (args: TArgs) => Promise<TResult>,
  invalidate: QueryKey[] = [],
  opts: { success?: string } = {},
) {
  const qc = useQueryClient();
  const [error, setError] = useState<ApiError | null>(null);
  const m = useMutation({
    mutationFn: fn,
    onMutate: () => setError(null),
    onError: (e) => setError(e instanceof ApiError ? e : new ApiError(0, { detail: String(e) })),
    onSuccess: async () => {
      if (opts.success) toast.success(opts.success);
      await Promise.all(invalidate.map((k) => qc.invalidateQueries({ queryKey: k })));
    },
  });
  return { ...m, error, clearError: () => setError(null) };
}
