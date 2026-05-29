import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchTopics,
  pinTopic,
  searchTopic,
  unpinTopic,
  type TopicCadence,
  type TopicSummary,
} from "../api";

export function useTopics() {
  const [topics, setTopics] = useState<TopicSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);

  const reload = useCallback(async (options?: { background?: boolean }) => {
    setError(null);
    const background = options?.background ?? false;
    if (background) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const res = await fetchTopics();
      setTopics(res.topics);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (background) {
        setRefreshing(false);
      } else {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function search(query: string, cadence: TopicCadence = "daily") {
    setSearching(true);
    setError(null);
    try {
      await searchTopic({ query, cadence });
      await reload({ background: true });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      throw e;
    } finally {
      setSearching(false);
    }
  }

  async function togglePin(id: string, pinned: boolean) {
    setError(null);
    const snapshot = topics;
    setTopics((list) =>
      list.map((t) => (t.id === id ? { ...t, pinned: !pinned } : t)),
    );
    try {
      if (pinned) await unpinTopic(id);
      else await pinTopic(id);
    } catch (e: unknown) {
      setTopics(snapshot);
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const pinned = useMemo(() => topics.filter((t) => t.pinned), [topics]);
  const trending = useMemo(
    () =>
      topics
        .filter((t) => !t.pinned)
        .sort((a, b) => (b.candidate_count ?? 0) - (a.candidate_count ?? 0)),
    [topics],
  );

  return {
    topics,
    pinned,
    trending,
    loading,
    refreshing,
    error,
    searching,
    reload,
    search,
    togglePin,
  };
}
