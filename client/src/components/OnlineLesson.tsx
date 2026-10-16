import type { QueryKey } from "@tanstack/react-query";
import { Link2, Video } from "lucide-react";
import { useEffect, useState } from "react";

import { Button, Card, ErrorAlert, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useAction } from "@/lib/hooks";
import type { Booking, Lesson } from "@/lib/types";

const EARLY_MS = 15 * 60_000;

function serviceName(url: string) {
  const host = (() => { try { return new URL(url).hostname; } catch { return ""; } })();
  if (host.endsWith("meet.google.com")) return "Google Meet";
  if (host.endsWith("zoom.us")) return "Zoom";
  if (host.includes("teams.")) return "Microsoft Teams";
  if (host.endsWith("whereby.com")) return "Whereby";
  return "video call";
}

/** Re-renders every 30 seconds so the Join button appears on time without a reload. */
function useNow() {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(t);
  }, []);
  return now;
}

/** LSN-07: "Join" opens from 15 minutes before an online lesson until it ends. */
export function JoinLessonButton({ lesson: l, className }: { lesson: Pick<Lesson, "is_online" | "online_link" | "scheduled_start" | "scheduled_end" | "status">; className?: string }) {
  const now = useNow();
  if (!l.is_online || !["scheduled", "in_progress"].includes(l.status)) return null;
  const start = new Date(l.scheduled_start).getTime();
  const open = now >= start - EARLY_MS && now <= new Date(l.scheduled_end).getTime();
  if (!open) return null;
  if (!l.online_link) return <p className={cn("text-xs font-medium text-amber-700", className)}>Online lesson — waiting for the tutor to add the video link.</p>;
  return (
    <a href={l.online_link} target="_blank" rel="noopener noreferrer"
      className={cn("inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white shadow-soft transition hover:bg-brand-700", className)}>
      <Video className="size-4" />Join on {serviceName(l.online_link)}
    </a>
  );
}

/** Tutor sets (or changes) the video link for an online booking. */
export function OnlineLinkCard({ booking: b, invalidate }: { booking: Booking; invalidate: QueryKey[] }) {
  const [link, setLink] = useState(b.online_link);
  const save = useAction(() => api.patch(`/bookings/${b.id}/online-link/`, { online_link: link.trim() }), invalidate,
    { success: "Link saved — the family has been notified" });
  if (!b.is_online || !["active", "offered"].includes(b.status)) return null;
  return (
    <Card title="Online lesson link" icon={Video} subtitle="One link for every lesson in this package. Google Meet, Zoom, Teams or Whereby.">
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <ErrorAlert error={save.error} />
        <Input label="Meeting link" type="url" icon={Link2} placeholder="https://meet.google.com/…" value={link} onChange={(e) => setLink(e.target.value)} required />
        <Button type="submit" className="w-full" loading={save.isPending} disabled={!link.trim() || link.trim() === b.online_link}>
          {b.online_link ? "Update link" : "Save link"}
        </Button>
      </form>
    </Card>
  );
}
