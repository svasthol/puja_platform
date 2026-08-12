"use client";

import { useQuery, type UseQueryOptions } from "@tanstack/react-query";

import { fetchAdminMe } from "@/lib/api/admin";
import { isAuthenticated } from "@/lib/auth/tokens";
import type { AdminMe } from "@/lib/schemas/auth";

type Options = Pick<UseQueryOptions<AdminMe>, "enabled">;

export function useAdminMe(options?: Options) {
  return useQuery({
    queryKey: ["admin", "me"],
    queryFn: fetchAdminMe,
    enabled: options?.enabled ?? isAuthenticated(),
    staleTime: 60_000,
    retry: false,
  });
}
