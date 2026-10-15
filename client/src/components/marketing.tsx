import { ArrowRight, BadgeCheck, Bell, CheckCircle2, ChevronDown, Clock, KeyRound, MapPin, ShieldCheck, Sparkles, Star, Wallet } from "lucide-react";
import { AnimatePresence, animate, motion } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useInView } from "react-intersection-observer";

import { cn } from "@/lib/cn";

import { Avatar, ButtonLink } from "./ui";

export function Eyebrow({ children, light, className }: { children: ReactNode; light?: boolean; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-xs font-semibold tracking-wide ring-1",
      light ? "bg-white/10 text-gold-200 ring-white/15 backdrop-blur" : "bg-brand-50 text-brand-700 ring-brand-100", className)}>
      <Sparkles className="size-3.5" />
      {children}
    </span>
  );
}

export function SectionHeading({ eyebrow, title, subtitle, light, align = "center", className }: { eyebrow?: string; title: ReactNode; subtitle?: ReactNode; light?: boolean; align?: "center" | "left"; className?: string }) {
  return (
    <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-80px" }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      className={cn("max-w-3xl", align === "center" && "mx-auto text-center", className)}>
      {eyebrow && <Eyebrow light={light}>{eyebrow}</Eyebrow>}
      <h2 className={cn("mt-4 font-display text-3xl leading-[1.1] font-bold text-balance sm:text-[2.6rem]", light ? "text-white" : "text-ink-950")}>{title}</h2>
      {subtitle && <p className={cn("mt-4 text-lg leading-relaxed text-balance", light ? "text-brand-100/80" : "text-ink-500")}>{subtitle}</p>}
    </motion.div>
  );
}

/** Hero for interior marketing pages. */
export function PageHero({ eyebrow, title, subtitle, dark, children }: { eyebrow?: string; title: ReactNode; subtitle?: ReactNode; dark?: boolean; children?: ReactNode }) {
  return (
    <section className={cn("relative overflow-hidden", dark ? "grain bg-brand-950 pt-[72px] text-white" : "bg-gradient-to-b from-sand to-cream")}>
      <div className={cn("pointer-events-none absolute inset-0", dark ? "bg-grid opacity-60" : "bg-grid-dark opacity-70 [mask-image:linear-gradient(to_bottom,black,transparent)]")} />
      {dark && <>
        <div className="absolute -top-32 -right-32 size-[30rem] rounded-full bg-brand-500/25 blur-3xl" />
        <div className="absolute -bottom-40 -left-20 size-[26rem] rounded-full bg-gold-400/10 blur-3xl" />
      </>}
      <div className="relative mx-auto max-w-5xl px-4 py-20 text-center sm:px-6 sm:py-24">
        {eyebrow && <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}><Eyebrow light={dark}>{eyebrow}</Eyebrow></motion.div>}
        <motion.h1 initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05, duration: 0.6 }}
          className={cn("mt-5 font-display text-4xl leading-[1.05] font-bold text-balance sm:text-6xl", dark ? "text-white" : "text-ink-950")}>{title}</motion.h1>
        {subtitle && <motion.p initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12, duration: 0.6 }}
          className={cn("mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-balance sm:text-xl", dark ? "text-brand-100/80" : "text-ink-500")}>{subtitle}</motion.p>}
        {children && <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="mt-9">{children}</motion.div>}
      </div>
    </section>
  );
}

/** Number that counts up when it scrolls into view. */
export function Counter({ to, suffix = "", prefix = "", duration = 1.6 }: { to: number; suffix?: string; prefix?: string; duration?: number }) {
  const { ref, inView } = useInView({ triggerOnce: true, threshold: 0.4 });
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (!inView) return;
    const controls = animate(0, to, { duration, ease: [0.22, 1, 0.36, 1], onUpdate: (v) => setValue(Math.round(v)) });
    return () => controls.stop();
  }, [inView, to, duration]);
  return <span ref={ref}>{prefix}{value.toLocaleString("en-NG")}{suffix}</span>;
}

export function Marquee({ items, className }: { items: string[]; className?: string }) {
  const row = [...items, ...items];
  return (
    <div className={cn("relative overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_10%,black_90%,transparent)]", className)}>
      <div className="flex w-max animate-marquee gap-3 hover:[animation-play-state:paused]">
        {row.map((t, i) => (
          <span key={i} className="flex items-center gap-2 rounded-full bg-white px-5 py-2.5 font-display text-[15px] font-semibold whitespace-nowrap text-ink-700 shadow-soft ring-1 ring-ink-100">
            <span className="size-1.5 rounded-full bg-gold-400" /> {t}
          </span>
        ))}
      </div>
    </div>
  );
}

export function FaqAccordion({ items }: { items: { q: string; a: string }[] }) {
  const [open, setOpen] = useState<number | null>(0);
  return (
    <div className="divide-y divide-ink-100 overflow-hidden rounded-3xl border border-ink-100 bg-white shadow-soft">
      {items.map((it, i) => (
        <div key={i}>
          <button onClick={() => setOpen(open === i ? null : i)} aria-expanded={open === i}
            className="flex w-full items-center justify-between gap-4 px-6 py-5 text-left transition hover:bg-ink-50/50">
            <span className="font-display text-[17px] font-semibold text-ink-900">{it.q}</span>
            <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-full transition", open === i ? "rotate-180 bg-brand-600 text-white" : "bg-ink-100 text-ink-600")}>
              <ChevronDown className="size-4" />
            </span>
          </button>
          <AnimatePresence initial={false}>
            {open === i && (
              <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }} className="overflow-hidden">
                <p className="px-6 pb-6 leading-relaxed text-ink-600">{it.a}</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      ))}
    </div>
  );
}

export function CtaBand({ title, subtitle, primary, secondary }: { title: ReactNode; subtitle: ReactNode; primary: { to: string; label: string }; secondary?: { to: string; label: string } }) {
  return (
    <section className="px-4 pb-20 sm:px-6">
      <motion.div initial={{ opacity: 0, y: 30, scale: 0.98 }} whileInView={{ opacity: 1, y: 0, scale: 1 }} viewport={{ once: true }} transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        className="grain relative mx-auto max-w-6xl overflow-hidden rounded-[2rem] bg-gradient-to-br from-brand-700 via-brand-800 to-brand-950 px-6 py-14 text-center shadow-lift sm:px-14 sm:py-20">
        <div className="bg-grid pointer-events-none absolute inset-0 opacity-60" />
        <div className="absolute -top-24 -right-16 size-80 rounded-full bg-gold-400/20 blur-3xl" />
        <div className="absolute -bottom-24 -left-16 size-80 rounded-full bg-brand-400/25 blur-3xl" />
        <div className="relative">
          <h2 className="mx-auto max-w-3xl font-display text-3xl leading-tight font-bold text-balance text-white sm:text-5xl">{title}</h2>
          <p className="mx-auto mt-5 max-w-xl text-lg text-brand-100/80">{subtitle}</p>
          <div className="mt-9 flex flex-wrap justify-center gap-3">
            <ButtonLink to={primary.to} variant="accent" size="lg" iconRight={ArrowRight}>{primary.label}</ButtonLink>
            {secondary && <ButtonLink to={secondary.to} variant="outline-light" size="lg">{secondary.label}</ButtonLink>}
          </div>
        </div>
      </motion.div>
    </section>
  );
}

/**
 * Illustrative product preview for the hero: how a lesson looks in the parent's app.
 * Names and numbers are placeholders, not real users.
 */
export function HeroMockup() {
  const [checkedIn, setCheckedIn] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    timer.current = window.setInterval(() => setCheckedIn((c) => !c), 3600);
    return () => window.clearInterval(timer.current);
  }, []);
  return (
    <div className="relative mx-auto w-full max-w-[480px] pt-12 pb-24 sm:px-8" aria-hidden="true">
      {/* Glow */}
      <div className="absolute inset-8 rounded-full bg-brand-400/30 blur-3xl" />

      {/* Main card: today's lesson */}
      <motion.div initial={{ opacity: 0, y: 30, rotate: -1.5 }} animate={{ opacity: 1, y: 0, rotate: -1.5 }} transition={{ delay: 0.3, duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
        className="relative mx-auto w-full max-w-[400px] rounded-[1.75rem] bg-white p-6 shadow-[0_30px_80px_-20px_rgb(0_0_0/0.55)]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Avatar name="Tutor Example" size={46} />
            <div>
              <p className="flex items-center gap-1.5 font-display font-semibold text-ink-950">Mr. T. Adeyemi <BadgeCheck className="size-4 fill-brand-500 text-white" /></p>
              <p className="text-xs text-ink-500">Mathematics · JSS2 · Today 4:00 PM</p>
            </div>
          </div>
          <span className="flex items-center gap-1 rounded-full bg-gold-50 px-2 py-1 text-xs font-bold text-amber-800"><Star className="size-3 fill-gold-400 text-gold-400" /> 4.9</span>
        </div>

        <div className="mt-5 rounded-2xl bg-gradient-to-br from-brand-50 to-white p-4 ring-1 ring-brand-100">
          <p className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-brand-700 uppercase"><KeyRound className="size-3.5" /> Today's check-in code</p>
          <div className="mt-2 flex gap-1.5">
            {"482913".split("").map((d, i) => (
              <motion.span key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6 + i * 0.06 }}
                className="flex h-12 min-w-0 flex-1 items-center justify-center rounded-xl bg-white font-display text-2xl font-bold text-ink-950 shadow-soft ring-1 ring-ink-100">{d}</motion.span>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-ink-500">Only you can see this. Give it to the tutor when they arrive.</p>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          {[["ID verified", ShieldCheck], ["Background", CheckCircle2], ["Tested", Sparkles]].map(([label, Icon]) => {
            const I = Icon as typeof ShieldCheck;
            return (
              <div key={label as string} className="rounded-xl bg-ink-50 px-2 py-2.5">
                <I className="mx-auto size-4 text-brand-600" />
                <p className="mt-1 text-[11px] font-semibold text-ink-700">{label as string}</p>
              </div>
            );
          })}
        </div>
      </motion.div>

      {/* Floating: check-in notification */}
      <motion.div initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.9, duration: 0.6 }}
        className="absolute top-0 right-0 z-10 w-64 animate-float rounded-2xl bg-white/95 p-3.5 shadow-lift ring-1 ring-ink-100 backdrop-blur sm:-right-10">
        <AnimatePresence mode="wait">
          <motion.div key={String(checkedIn)} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} className="flex items-start gap-2.5">
            <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-full", checkedIn ? "animate-pulse-ring bg-brand-500 text-white" : "bg-gold-100 text-gold-600")}>
              {checkedIn ? <CheckCircle2 className="size-4" /> : <Bell className="size-4" />}
            </span>
            <div>
              <p className="text-[13px] font-semibold text-ink-900">{checkedIn ? "Tutor checked in · 3:58 PM" : "Lesson in 2 hours"}</p>
              <p className="text-[11px] text-ink-500">{checkedIn ? "Location confirmed at your address" : "Your codes are ready in the app"}</p>
            </div>
          </motion.div>
        </AnimatePresence>
      </motion.div>

      {/* Floating: escrow */}
      <motion.div initial={{ opacity: 0, x: -30 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 1.1, duration: 0.6 }}
        className="absolute bottom-0 left-0 z-10 w-56 rounded-2xl bg-ink-950 p-4 text-white shadow-lift" style={{ animation: "float 7s ease-in-out infinite" }}>
        <p className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-gold-300 uppercase"><Wallet className="size-3.5" /> Held safely</p>
        <p className="mt-1 font-display text-2xl font-bold">₦48,000</p>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
          <motion.div initial={{ width: 0 }} animate={{ width: "37%" }} transition={{ delay: 1.5, duration: 1.2 }} className="h-full rounded-full bg-gradient-to-r from-brand-400 to-gold-300" />
        </div>
        <p className="mt-1.5 text-[11px] text-white/60">3 of 8 lessons confirmed & released</p>
      </motion.div>

      {/* Floating: location chip */}
      <motion.div initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 1.3 }}
        className="absolute right-2 bottom-10 z-10 hidden items-center gap-1.5 rounded-full bg-white px-3 py-2 text-xs font-semibold text-ink-700 shadow-lift ring-1 ring-ink-100 sm:flex">
        <MapPin className="size-3.5 text-brand-600" /> Lekki Phase 1 <Clock className="ml-1 size-3.5 text-ink-400" /> 90 min
      </motion.div>
    </div>
  );
}
