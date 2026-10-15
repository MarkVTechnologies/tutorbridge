import { Check, ChevronRight, KeyRound, type LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { cn } from "@/lib/cn";
import { timeOnly } from "@/lib/format";
import type { Lesson } from "@/lib/types";

import { StatusBadge } from "./ui";

const TZ = "Africa/Lagos";

/** Gradient greeting banner at the top of dashboards. */
export function WelcomeBanner({ greeting, title, subtitle, actions, aside }: { greeting?: string; title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; aside?: ReactNode }) {
  return (
    <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45 }}
      className="grain relative mb-8 overflow-hidden rounded-[2rem] bg-gradient-to-br from-brand-700 via-brand-800 to-brand-950 p-7 text-white shadow-lift sm:p-9">
      <div className="bg-grid pointer-events-none absolute inset-0 opacity-50" />
      <div className="absolute -top-24 -right-10 size-72 rounded-full bg-gold-400/20 blur-3xl" />
      <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
        <div className="max-w-xl">
          {greeting && <p className="text-sm font-medium text-brand-200">{greeting}</p>}
          <h1 className="mt-1 font-display text-3xl font-bold sm:text-4xl">{title}</h1>
          {subtitle && <div className="mt-2 text-brand-100/80">{subtitle}</div>}
          {actions && <div className="mt-6 flex flex-wrap gap-2">{actions}</div>}
        </div>
        {aside && <div className="lg:w-[360px]">{aside}</div>}
      </div>
    </motion.section>
  );
}

export function greeting() {
  const h = Number(new Date().toLocaleString("en-GB", { timeZone: TZ, hour: "2-digit", hour12: false }));
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

/** Calendar-style date block. */
export function DateChip({ iso, tone = "light" }: { iso: string; tone?: "light" | "dark" | "brand" }) {
  const d = new Date(iso);
  const day = d.toLocaleDateString("en-GB", { timeZone: TZ, day: "numeric" });
  const mon = d.toLocaleDateString("en-GB", { timeZone: TZ, month: "short" });
  const wd = d.toLocaleDateString("en-GB", { timeZone: TZ, weekday: "short" });
  return (
    <div className={cn("flex w-14 shrink-0 flex-col items-center overflow-hidden rounded-2xl text-center ring-1",
      tone === "brand" ? "bg-brand-600 text-white ring-brand-600" : tone === "dark" ? "bg-white/10 text-white ring-white/15" : "bg-white text-ink-900 ring-ink-100 shadow-soft")}>
      <span className={cn("w-full py-0.5 text-[10px] font-bold tracking-wider uppercase", tone === "light" ? "bg-brand-50 text-brand-700" : "bg-black/15")}>{mon}</span>
      <span className="font-display text-xl leading-7 font-bold">{day}</span>
      <span className={cn("pb-1 text-[10px] font-medium", tone === "light" ? "text-ink-500" : "text-white/70")}>{wd}</span>
    </div>
  );
}

/** One upcoming lesson as a row; links to the lesson/booking. */
export function LessonRow({ lesson, to, subtitle }: { lesson: Lesson; to: string; subtitle?: ReactNode }) {
  return (
    <Link to={to} className="group flex items-center gap-4 rounded-2xl p-2.5 transition hover:bg-ink-50">
      <DateChip iso={lesson.scheduled_start} />
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-ink-900">{timeOnly(lesson.scheduled_start)} – {timeOnly(lesson.scheduled_end)}</p>
        <p className="truncate text-sm text-ink-500">{subtitle}</p>
      </div>
      <StatusBadge status={lesson.status} label={lesson.status_display} />
      <ChevronRight className="size-4 text-ink-300 transition group-hover:translate-x-0.5 group-hover:text-ink-500" />
    </Link>
  );
}

/** Horizontal progress tracker for multi-stage statuses. */
export function StatusStepper({ steps, current }: { steps: { key: string; label: string }[]; current: string }) {
  const idx = Math.max(0, steps.findIndex((s) => s.key === current));
  return (
    <ol className="flex items-center gap-1.5">
      {steps.map((s, i) => {
        const done = i < idx || (i === idx && i === steps.length - 1);
        const active = i === idx && !done;
        return (
          <li key={s.key} className="flex flex-1 items-center gap-1.5 last:flex-none">
            <div className="flex items-center gap-2">
              <span className={cn("flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-bold transition",
                done ? "bg-brand-600 text-white" : active ? "bg-gold-300 text-ink-950 ring-4 ring-gold-100" : "bg-ink-100 text-ink-400")}>
                {done ? <Check className="size-3.5" strokeWidth={3} /> : i + 1}
              </span>
              <span className={cn("hidden text-xs font-semibold whitespace-nowrap sm:inline", done || active ? "text-ink-800" : "text-ink-400")}>{s.label}</span>
            </div>
            {i < steps.length - 1 && <span className={cn("h-0.5 min-w-4 flex-1 rounded-full", i < idx ? "bg-brand-500" : "bg-ink-100")} />}
          </li>
        );
      })}
    </ol>
  );
}

/** Big, legible check-in/out code display for the parent. */
export function CodeDisplay({ label, code, dark }: { label: string; code: string; dark?: boolean }) {
  return (
    <div>
      <p className={cn("flex items-center gap-1.5 text-[11px] font-semibold tracking-wider uppercase", dark ? "text-gold-200" : "text-brand-700")}><KeyRound className="size-3.5" /> {label}</p>
      <div className="mt-2 flex gap-1.5">
        {code.split("").map((d, i) => (
          <span key={i} className={cn("flex h-12 w-10 items-center justify-center rounded-xl font-display text-2xl font-bold sm:w-11",
            dark ? "bg-white/10 text-white ring-1 ring-white/15" : "bg-white text-ink-950 shadow-soft ring-1 ring-ink-100")}>{d}</span>
        ))}
      </div>
    </div>
  );
}

/** Quick-action tile used on dashboards. */
export function QuickAction({ to, icon: Icon, title, body }: { to: string; icon: LucideIcon; title: string; body: string }) {
  return (
    <Link to={to} className="group flex items-start gap-4 rounded-3xl border border-ink-100 bg-white p-5 shadow-soft transition hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-lift">
      <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 transition group-hover:bg-brand-600 group-hover:text-white"><Icon className="size-5" /></span>
      <div className="min-w-0">
        <p className="font-semibold text-ink-900">{title}</p>
        <p className="mt-0.5 text-sm text-ink-500">{body}</p>
      </div>
      <ChevronRight className="mt-1 ml-auto size-4 shrink-0 text-ink-300 transition group-hover:translate-x-0.5 group-hover:text-brand-600" />
    </Link>
  );
}
