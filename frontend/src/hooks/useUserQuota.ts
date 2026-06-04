/**
 * Reads the current user's paid-tier daily quota + plan tier from the backend.
 *
 * Fetches once when the user becomes authenticated, and exposes a `refresh()`
 * that callers invoke after a successful session-create / model-switch so the
 * chip reflects the new count without a full page reload.
 */
import { useCallback, useEffect, useState } from 'react';
import { useAgentStore } from '@/store/agentStore';
import { apiFetch } from '@/utils/api';

export type PlanTier = 'free' | 'pro';

export interface UserQuota {
  plan: PlanTier;
  paidUsedToday: number;
  paidDailyCap: number;
  paidRemaining: number;
}

export function useUserQuota({ enabled = true }: { enabled?: boolean } = {}) {
  const user = useAgentStore((s) => s.user);
  const [quota, setQuota] = useState<UserQuota | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!enabled || !user?.authenticated) return;
    setLoading(true);
    try {
      const res = await apiFetch('/api/user/quota');
      if (!res.ok) return;
      const data = await res.json();
      setQuota({
        plan: (data.plan ?? 'free') as PlanTier,
        paidUsedToday: data.paid_used_today ?? 0,
        paidDailyCap: data.paid_daily_cap ?? 0,
        paidRemaining: data.paid_remaining ?? 0,
      });
    } catch {
      /* backend unreachable — leave previous value */
    } finally {
      setLoading(false);
    }
  }, [enabled, user?.authenticated]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { quota, loading, refresh };
}
