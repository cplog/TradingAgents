import { useEffect, useState } from "react";

/**
 * Track which heading anchor (by id) is currently in view.
 *
 * Scrollspy that picks the topmost section whose start has scrolled past the
 * "top trigger" line — a band ~25% from the viewport top. This matches how
 * readers actually use a sticky TOC: the active item is the one whose content
 * they're currently reading, not the one that's about to enter the screen.
 */
export function useActiveSection(ids: ReadonlyArray<string>): string | null {
  const [active, setActive] = useState<string | null>(ids[0] ?? null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (ids.length === 0) {
      setActive(null);
      return;
    }
    if (typeof IntersectionObserver === "undefined") {
      setActive(ids[0] ?? null);
      return;
    }

    const elements = ids
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => el != null);
    if (elements.length === 0) {
      setActive(ids[0] ?? null);
      return;
    }

    const visible = new Map<string, number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = (entry.target as HTMLElement).id;
          if (!id) continue;
          if (entry.isIntersecting) {
            visible.set(id, entry.intersectionRatio);
          } else {
            visible.delete(id);
          }
        }
        if (visible.size === 0) return;
        const ordered = ids.filter((id) => visible.has(id));
        if (ordered.length > 0) setActive(ordered[0]);
      },
      {
        rootMargin: "-12% 0px -70% 0px",
        threshold: [0, 0.5, 1],
      },
    );

    for (const el of elements) observer.observe(el);
    return () => observer.disconnect();
  }, [ids]);

  return active;
}
