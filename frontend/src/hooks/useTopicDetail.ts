import { useCallback, useEffect, useState } from "react";
import {
  deleteTopic,
  fetchTopic,
  fetchTopicRuns,
  pinTopic,
  refreshTopic,
  unpinTopic,
  updateTopic,
  type Topic,
  type TopicCadence,
  type TopicRun,
} from "../api";

export function useTopicDetail(topicId: string) {
  const [topic, setTopic] = useState<Topic | null>(null);
  const [latestRun, setLatestRun] = useState<TopicRun | null>(null);
  const [runs, setRuns] = useState<TopicRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!topicId) return;
    setError(null);
    setLoading(true);
    try {
      const [detail, history] = await Promise.all([
        fetchTopic(topicId),
        fetchTopicRuns(topicId),
      ]);
      setTopic(detail.topic);
      setLatestRun(detail.latest_run);
      setRuns(history.runs);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [topicId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const refresh = useCallback(async () => {
    if (!topicId) return;
    setRefreshing(true);
    setError(null);
    try {
      const res = await refreshTopic(topicId);
      const runAt = res.run.completed_at ?? res.run.started_at;
      setLatestRun(res.run);
      setRuns((prev) => {
        const rest = prev.filter((r) => r.run_id !== res.run.run_id);
        return [res.run, ...rest];
      });
      setTopic((prev) =>
        prev
          ? {
              ...prev,
              last_run_at: runAt,
              last_refresh_at: runAt,
            }
          : prev,
      );
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  }, [topicId]);

  const patch = useCallback(
    async (body: { label?: string; query?: string; cadence?: TopicCadence }) => {
      setError(null);
      const res = await updateTopic(topicId, body);
      setTopic(res.topic);
      setLatestRun(res.latest_run);
    },
    [topicId],
  );

  const togglePin = useCallback(async () => {
    if (!topic) return;
    const snapshot = topic;
    setTopic({ ...snapshot, pinned: !snapshot.pinned });
    setError(null);
    try {
      const res = snapshot.pinned ? await unpinTopic(topicId) : await pinTopic(topicId);
      setTopic(res.topic);
    } catch (e: unknown) {
      setTopic(snapshot);
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [topicId, topic]);

  const remove = useCallback(async () => {
    await deleteTopic(topicId);
  }, [topicId]);

  return {
    topic,
    latestRun,
    runs,
    loading,
    refreshing,
    error,
    reload,
    refresh,
    patch,
    togglePin,
    remove,
  };
}
