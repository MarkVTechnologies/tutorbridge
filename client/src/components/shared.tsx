import { BadgeCheck, Clock, MapPin, Sparkles, Upload } from "lucide-react";
import { motion } from "motion/react";
import { useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { cn } from "@/lib/cn";
import { WEEKDAYS_SHORT, naira } from "@/lib/format";
import type { Slot, TutorPublic } from "@/lib/types";

import { Avatar, Badge, Button, Stars, TierBadge } from "./ui";

const TIMES = Array.from({ length: 27 }, (_, i) => {
  const mins = 7 * 60 + i * 30; // 07:00 → 20:00
  return `${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;
});

/** Weekly recurring slots: pick days and a start time for each. */
export function ScheduleEditor({ value, onChange }: { value: Slot[]; onChange: (v: Slot[]) => void }) {
  const toggle = (wd: number) => {
    const exists = value.find((s) => s.weekday === wd);
    onChange(exists ? value.filter((s) => s.weekday !== wd) : [...value, { weekday: wd, start: "16:00" }].sort((a, b) => a.weekday - b.weekday));
  };
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-7 gap-1.5" role="group" aria-label="Lesson days">
        {WEEKDAYS_SHORT.map((d, i) => {
          const on = value.some((s) => s.weekday === i);
          return (
            <motion.button whileTap={{ scale: 0.94 }} key={d} type="button" aria-pressed={on} onClick={() => toggle(i)}
              className={cn("min-h-12 rounded-2xl text-sm font-semibold ring-1 transition", on ? "bg-brand-600 text-white shadow-glow ring-brand-600" : "bg-white text-ink-600 ring-ink-200 hover:ring-ink-300")}>
              {d}
            </motion.button>
          );
        })}
      </div>
      {value.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {value.map((s) => (
            <motion.div layout initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} key={s.weekday} className="flex items-center gap-3 rounded-2xl bg-ink-50/80 px-3 py-2">
              <span className="w-10 text-sm font-semibold text-ink-800">{WEEKDAYS_SHORT[s.weekday]}</span>
              <Clock className="size-4 text-ink-400" />
              <select className="input py-1.5" aria-label={`Start time on ${WEEKDAYS_SHORT[s.weekday]}`} value={s.start}
                onChange={(e) => onChange(value.map((x) => (x.weekday === s.weekday ? { ...x, start: e.target.value } : x)))}>
                {TIMES.map((t) => <option key={t}>{t}</option>)}
              </select>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}

export function TutorAvatar({ tutor, size = 64 }: { tutor: Pick<TutorPublic, "name" | "photo_url">; size?: number }) {
  return <Avatar name={tutor.name} src={tutor.photo_url} size={size} />;
}

export function TutorCard({ tutor, action, extra, highlight }: { tutor: TutorPublic; action?: ReactNode; extra?: ReactNode; highlight?: boolean }) {
  const subjects = [...new Set(tutor.subjects.map((s) => s.subject_name))];
  const levels = [...new Set(tutor.subjects.map((s) => s.level_name))];
  return (
    <motion.article whileHover={{ y: -2 }} transition={{ type: "spring", stiffness: 400, damping: 30 }}
      className={cn("relative flex flex-col gap-5 rounded-3xl border bg-white p-6 shadow-soft transition-shadow hover:shadow-lift sm:flex-row",
        highlight ? "border-brand-300 ring-4 ring-brand-50" : "border-ink-100")}>
      {highlight && <span className="absolute -top-3 left-6 inline-flex items-center gap-1 rounded-full bg-gold-300 px-3 py-1 text-xs font-bold text-ink-950 shadow-soft"><Sparkles className="size-3.5" /> Top match for you</span>}
      <div className="relative self-start">
        <Avatar name={tutor.name} src={tutor.photo_url} size={84} />
        <BadgeCheck className="absolute -right-1 -bottom-1 size-7 fill-brand-500 text-white" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-display text-xl font-bold text-ink-950"><Link to={`/tutors/${tutor.id}`} className="hover:text-brand-700">{tutor.name}</Link></h3>
          <TierBadge tier={tutor.tier} />
          {tutor.accepts_special_needs && <Badge tone="blue">Special needs support</Badge>}
        </div>
        <p className="mt-1 text-ink-600">{tutor.headline}</p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {subjects.map((s) => <Badge key={s} tone="green">{s}</Badge>)}
          <span className="self-center text-xs text-ink-400">{levels.join(" · ")}</span>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-ink-600">
          {tutor.rating_count > 0 ? (
            <span className="flex items-center gap-1.5"><Stars value={Number(tutor.rating_avg)} /><strong className="text-ink-900">{Number(tutor.rating_avg).toFixed(1)}</strong> ({tutor.rating_count})</span>
          ) : <span className="flex items-center gap-1.5 text-gold-600"><Sparkles className="size-4" /> New tutor</span>}
          <span className="flex items-center gap-1.5"><Clock className="size-4 text-ink-400" />{Math.round(Number(tutor.hours_taught))} hrs taught</span>
          {tutor.home_area_name && <span className="flex items-center gap-1.5"><MapPin className="size-4 text-ink-400" />{tutor.home_area_name}</span>}
        </div>
        {tutor.badges.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5 border-t border-ink-100 pt-4 text-xs font-medium text-ink-600">
            {tutor.badges.map((b) => <span key={b} className="flex items-center gap-1"><BadgeCheck className="size-3.5 text-brand-500" />{b}</span>)}
          </div>
        )}
        {extra}
      </div>
      <div className="flex shrink-0 flex-row items-center justify-between gap-3 border-t border-ink-100 pt-4 sm:flex-col sm:items-end sm:justify-start sm:border-0 sm:pt-0">
        <p className="font-display text-2xl font-bold text-ink-950">{naira(tutor.hourly_rate_kobo)}<span className="text-sm font-normal text-ink-500">/hour</span></p>
        {action}
      </div>
    </motion.article>
  );
}

export function FileUpload({ label, accept = ".pdf,.jpg,.jpeg,.png", onUpload, capture }: { label: string; accept?: string; onUpload: (f: File) => Promise<unknown>; capture?: "user" | "environment" }) {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <div>
      <input ref={ref} type="file" accept={accept} capture={capture} className="hidden" aria-label={label}
        onChange={async (e) => {
          const f = e.target.files?.[0];
          if (!f) return;
          if (f.size > 5 * 1024 * 1024) { setErr("Files must be 5 MB or smaller."); return; }
          setBusy(true);
          setErr(null);
          try { await onUpload(f); } catch (x) { setErr((x as Error).message); } finally { setBusy(false); if (ref.current) ref.current.value = ""; }
        }} />
      <Button type="button" size="sm" variant="secondary" icon={Upload} loading={busy} onClick={() => ref.current?.click()}>{label}</Button>
      {err && <p className="mt-1 text-sm text-red-600">{err}</p>}
    </div>
  );
}

export function KeyValue({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-8 gap-y-4 text-sm sm:grid-cols-2">
      {items.map(([k, v]) => (
        <div key={k}>
          <dt className="text-xs font-medium tracking-wide text-ink-400 uppercase">{k}</dt>
          <dd className="mt-0.5 font-medium text-ink-900">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
