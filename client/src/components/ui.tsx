import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Inbox, Info, Loader2, Star, X, XCircle, type LucideIcon } from "lucide-react";
import { AnimatePresence, motion, type HTMLMotionProps } from "motion/react";
import { useEffect, useId, useRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { Link } from "react-router-dom";

import type { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";

/** @deprecated use cn */
export const cx = cn;

// --- Buttons ---------------------------------------------------------------

type Variant = "primary" | "secondary" | "danger" | "ghost" | "accent" | "dark" | "outline-light";
type Size = "sm" | "md" | "lg";
const variants: Record<Variant, string> = {
  primary: "bg-brand-600 text-white shadow-[0_1px_0_rgb(255_255_255/0.15)_inset,0_6px_16px_-6px_rgb(19_111_76/0.6)] hover:bg-brand-700 disabled:bg-brand-300 disabled:shadow-none",
  secondary: "bg-white text-ink-800 ring-1 ring-ink-200 shadow-soft hover:bg-ink-50 hover:ring-ink-300 disabled:text-ink-400",
  danger: "bg-red-600 text-white shadow-[0_6px_16px_-6px_rgb(220_38_38/0.6)] hover:bg-red-700 disabled:bg-red-300",
  ghost: "text-brand-700 hover:bg-brand-50 disabled:text-ink-400",
  accent: "bg-gold-300 text-ink-950 shadow-[0_6px_20px_-6px_rgb(249_163_37/0.7)] hover:bg-gold-400",
  dark: "bg-ink-950 text-white hover:bg-ink-800",
  "outline-light": "text-white ring-1 ring-white/30 hover:bg-white/10",
};
const sizes: Record<Size, string> = {
  sm: "min-h-9 px-3 text-[13px] gap-1.5 rounded-lg",
  md: "min-h-11 px-4.5 text-sm gap-2 rounded-xl",
  lg: "min-h-13 px-6 text-base gap-2.5 rounded-2xl",
};
const base = "inline-flex shrink-0 items-center justify-center font-semibold whitespace-nowrap transition-all duration-200 disabled:cursor-not-allowed active:scale-[0.98]";

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; loading?: boolean; icon?: LucideIcon; iconRight?: LucideIcon };

export function Button({ variant = "primary", size = "md", loading, icon: Icon, iconRight: IconRight, className, children, ...rest }: BtnProps) {
  return (
    <button {...rest} disabled={rest.disabled || loading} className={cn(base, sizes[size], variants[variant], className)}>
      {loading ? <Loader2 className="size-4 animate-spin" /> : Icon && <Icon className="size-4" strokeWidth={2.25} />}
      {children}
      {IconRight && !loading && <IconRight className="size-4 transition-transform group-hover:translate-x-0.5" strokeWidth={2.25} />}
    </button>
  );
}

export function ButtonLink({ to, variant = "primary", size = "md", className, children, icon: Icon, iconRight: IconRight }: { to: string; variant?: Variant; size?: Size; className?: string; children: ReactNode; icon?: LucideIcon; iconRight?: LucideIcon }) {
  return (
    <Link to={to} className={cn("group", base, sizes[size], variants[variant], className)}>
      {Icon && <Icon className="size-4" strokeWidth={2.25} />}
      {children}
      {IconRight && <IconRight className="size-4 transition-transform group-hover:translate-x-0.5" strokeWidth={2.25} />}
    </Link>
  );
}

// --- Feedback --------------------------------------------------------------

export function Spinner({ small, className }: { small?: boolean; className?: string }) {
  return <Loader2 role="status" aria-label="Loading" className={cn("animate-spin text-brand-600", small ? "size-4" : "size-6", className)} />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-xl bg-ink-100/80", className)} />;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-sm text-ink-500">
      <Spinner />
      {label}
    </div>
  );
}

const alertStyles = {
  red: { box: "bg-red-50 text-red-900 ring-red-200", icon: XCircle, iconCls: "text-red-500" },
  green: { box: "bg-brand-50 text-brand-900 ring-brand-200", icon: CheckCircle2, iconCls: "text-brand-500" },
  amber: { box: "bg-gold-50 text-amber-950 ring-gold-200", icon: AlertTriangle, iconCls: "text-gold-500" },
  blue: { box: "bg-sky-50 text-sky-950 ring-sky-200", icon: Info, iconCls: "text-sky-500" },
};

export function Alert({ tone = "red", children, title, className }: { tone?: keyof typeof alertStyles; children: ReactNode; title?: string; className?: string }) {
  const s = alertStyles[tone];
  const Icon = s.icon;
  return (
    <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} role={tone === "red" ? "alert" : "status"}
      className={cn("flex gap-3 rounded-2xl px-4 py-3.5 text-sm ring-1 ring-inset", s.box, className)}>
      <Icon className={cn("mt-0.5 size-5 shrink-0", s.iconCls)} />
      <div className="min-w-0">
        {title && <p className="mb-0.5 font-semibold">{title}</p>}
        <div className="leading-relaxed">{children}</div>
      </div>
    </motion.div>
  );
}

export function ErrorAlert({ error }: { error: ApiError | Error | null | undefined }) {
  if (!error) return null;
  return <Alert>{error.message}</Alert>;
}

export function EmptyState({ title, children, action, icon: Icon = Inbox }: { title: string; children?: ReactNode; action?: ReactNode; icon?: LucideIcon }) {
  return (
    <div className="relative overflow-hidden rounded-3xl border border-dashed border-ink-200 bg-white/70 px-6 py-14 text-center">
      <div className="mx-auto mb-4 flex size-14 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 ring-8 ring-brand-50/50">
        <Icon className="size-6" />
      </div>
      <p className="font-display text-lg font-semibold text-ink-900">{title}</p>
      {children && <div className="mx-auto mt-1.5 max-w-md text-sm leading-relaxed text-ink-500">{children}</div>}
      {action && <div className="mt-6 flex justify-center">{action}</div>}
    </div>
  );
}

// --- Forms -----------------------------------------------------------------

export function Field({ label, hint, error, children, htmlFor }: { label: string; hint?: string; error?: string; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-[13px] font-semibold text-ink-700">{label}</label>
      {children}
      {hint && !error && <p className="text-xs leading-relaxed text-ink-500">{hint}</p>}
      {error && <p className="flex items-center gap-1 text-[13px] text-red-600"><AlertTriangle className="size-3.5" />{error}</p>}
    </div>
  );
}

export function Input({ label, hint, error, icon: Icon, className, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string; icon?: LucideIcon }) {
  const id = useId();
  return (
    <Field label={label} hint={hint} error={error} htmlFor={id}>
      <div className="relative">
        {Icon && <Icon className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-ink-400" />}
        <input id={id} className={cn("input", Icon && "pl-10", className)} aria-invalid={!!error} {...rest} />
      </div>
    </Field>
  );
}

export function Textarea({ label, hint, error, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; hint?: string; error?: string }) {
  const id = useId();
  return (
    <Field label={label} hint={hint} error={error} htmlFor={id}>
      <textarea id={id} className="input min-h-28 resize-y leading-relaxed" aria-invalid={!!error} {...rest} />
    </Field>
  );
}

export function Select({ label, hint, error, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement> & { label: string; hint?: string; error?: string }) {
  const id = useId();
  return (
    <Field label={label} hint={hint} error={error} htmlFor={id}>
      <select id={id} className="input" aria-invalid={!!error} {...rest}>
        {children}
      </select>
    </Field>
  );
}

export function Checkbox({ label, className, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode }) {
  return (
    <label className={cn("group flex cursor-pointer items-start gap-3 text-sm text-ink-700", className)}>
      <input type="checkbox" className="peer sr-only" {...rest} />
      <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md border-2 border-ink-300 bg-white transition peer-checked:border-brand-600 peer-checked:bg-brand-600 peer-focus-visible:ring-4 peer-focus-visible:ring-brand-100 [&>svg]:opacity-0 peer-checked:[&>svg]:opacity-100">
        <svg viewBox="0 0 12 12" className="size-3 text-white" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m2.5 6.5 2.5 2.5 4.5-6" /></svg>
      </span>
      <span className="leading-snug">{label}</span>
    </label>
  );
}

// --- Surfaces --------------------------------------------------------------

export function Card({ children, className, title, actions, subtitle, icon: Icon, ...rest }: { children: ReactNode; className?: string; title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; icon?: LucideIcon } & Omit<HTMLMotionProps<"section">, "title" | "children">) {
  return (
    <motion.section {...rest} className={cn("rounded-3xl border border-ink-100 bg-white p-5 shadow-soft sm:p-6", className)}>
      {(title || actions) && (
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            {Icon && <IconTile icon={Icon} size="sm" />}
            <div>
              {title && <h2 className="font-display text-lg font-semibold text-ink-900">{title}</h2>}
              {subtitle && <p className="text-sm text-ink-500">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </motion.section>
  );
}

const tileTones = {
  green: "bg-brand-50 text-brand-600 ring-brand-100",
  gold: "bg-gold-50 text-gold-600 ring-gold-100",
  blue: "bg-sky-50 text-sky-600 ring-sky-100",
  red: "bg-red-50 text-red-600 ring-red-100",
  violet: "bg-violet-50 text-violet-600 ring-violet-100",
  ink: "bg-ink-50 text-ink-700 ring-ink-100",
  dark: "bg-white/10 text-gold-300 ring-white/10",
};
export type TileTone = keyof typeof tileTones;

export function IconTile({ icon: Icon, tone = "green", size = "md", className }: { icon: LucideIcon; tone?: TileTone; size?: "sm" | "md" | "lg"; className?: string }) {
  const s = { sm: "size-9 rounded-xl [&>svg]:size-4.5", md: "size-11 rounded-2xl [&>svg]:size-5", lg: "size-14 rounded-2xl [&>svg]:size-6" }[size];
  return (
    <span className={cn("inline-flex shrink-0 items-center justify-center ring-1 ring-inset", tileTones[tone], s, className)}>
      <Icon strokeWidth={2} />
    </span>
  );
}

const tones = {
  green: "bg-brand-50 text-brand-700 ring-brand-200/70",
  amber: "bg-gold-50 text-amber-800 ring-gold-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  slate: "bg-ink-50 text-ink-600 ring-ink-200",
  blue: "bg-sky-50 text-sky-700 ring-sky-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200",
};
export type Tone = keyof typeof tones;

export function Badge({ tone = "slate", children, dot, className }: { tone?: Tone; children: ReactNode; dot?: boolean; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap ring-1 ring-inset", tones[tone], className)}>
      {dot && <span className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

const STATUS_TONES: Record<string, Tone> = {
  active: "green", confirmed: "green", completed: "green", success: "green", passed: "green", resolved: "green", approved: "green", accepted: "green", booked: "green", released: "green", paid_out: "green", shortlist_ready: "green", pass: "green",
  offered: "amber", awaiting_payment: "amber", submitted: "amber", matching: "amber", reassigning: "amber", under_review: "amber", interview: "amber", manual_review: "amber", invited: "amber", investigating: "amber",
  in_progress: "blue", scheduled: "blue", sent: "blue", suggested: "violet",
  pending: "slate", draft: "slate", reserved: "slate", initiated: "slate", cancelled: "slate", replaced: "slate", closed: "slate", refunded: "slate", applied: "slate", withdrawn: "slate", removed: "slate", abandoned: "slate",
  open: "red", failed: "red", fail: "red", rejected: "red", suspended: "red", banned: "red", no_show: "red", disputed: "red", declined: "red", partial: "red", urgent: "red", high: "red",
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const text = label ?? status.replace(/_/g, " ");
  return <Badge dot tone={STATUS_TONES[status] ?? "slate"}>{text.charAt(0).toUpperCase() + text.slice(1)}</Badge>;
}

export function PageHeader({ title, subtitle, actions, back, eyebrow }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; back?: { to: string; label: string }; eyebrow?: ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }} className="mb-7">
      {back && (
        <Link to={back.to} className="group mb-3 inline-flex items-center gap-1 text-sm font-medium text-ink-500 transition hover:text-brand-700">
          <ChevronLeft className="size-4 transition-transform group-hover:-translate-x-0.5" /> {back.label}
        </Link>
      )}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          {eyebrow && <p className="mb-1 text-xs font-semibold tracking-[0.14em] text-brand-600 uppercase">{eyebrow}</p>}
          <h1 className="font-display text-2xl font-bold text-ink-950 sm:text-[1.9rem]">{title}</h1>
          {subtitle && <div className="mt-1.5 text-[15px] text-ink-500">{subtitle}</div>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </motion.div>
  );
}

export function Stat({ label, value, hint, tone, icon, iconTone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "red" | "green"; icon?: LucideIcon; iconTone?: TileTone }) {
  return (
    <motion.div whileHover={{ y: -2 }} transition={{ type: "spring", stiffness: 400, damping: 25 }}
      className="relative overflow-hidden rounded-3xl border border-ink-100 bg-white p-5 shadow-soft">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[13px] font-medium text-ink-500">{label}</p>
        {icon && <IconTile icon={icon} tone={iconTone ?? (tone === "red" ? "red" : "green")} size="sm" />}
      </div>
      <p className={cn("mt-2 font-display text-[1.75rem] leading-none font-bold tracking-tight", tone === "red" ? "text-red-600" : tone === "green" ? "text-brand-700" : "text-ink-950")}>{value}</p>
      {hint && <p className="mt-2 text-xs text-ink-500">{hint}</p>}
    </motion.div>
  );
}

export function Modal({ open, onClose, title, children, footer, description }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; description?: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} onClose={onClose} onClick={(e) => e.target === ref.current && onClose()}
      className="m-auto w-[min(94vw,34rem)] overflow-visible bg-transparent p-0 backdrop:bg-ink-950/50 backdrop:backdrop-blur-sm">
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, scale: 0.96, y: 12 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.96 }} transition={{ type: "spring", stiffness: 380, damping: 30 }}
            className="flex max-h-[90vh] flex-col overflow-hidden rounded-3xl bg-white shadow-2xl">
            <div className="flex shrink-0 items-start justify-between gap-4 border-b border-ink-100 px-6 py-5">
              <div>
                <h2 className="font-display text-lg font-semibold text-ink-950">{title}</h2>
                {description && <p className="mt-0.5 text-sm text-ink-500">{description}</p>}
              </div>
              <button onClick={onClose} aria-label="Close" className="-m-1 rounded-xl p-1.5 text-ink-400 transition hover:bg-ink-50 hover:text-ink-700"><X className="size-5" /></button>
            </div>
            <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">{children}</div>
            {footer && <div className="flex shrink-0 flex-wrap justify-end gap-2 border-t border-ink-100 bg-ink-50/60 px-6 py-4">{footer}</div>}
          </motion.div>
        )}
      </AnimatePresence>
    </dialog>
  );
}

export function Table({ head, children, empty }: { head: ReactNode[]; children: ReactNode; empty?: boolean }) {
  return (
    <div className="overflow-hidden rounded-3xl border border-ink-100 bg-white shadow-soft">
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-ink-100 bg-ink-50/70">
              {head.map((h, i) => (
                <th key={i} scope="col" className="px-5 py-3.5 text-left text-xs font-semibold tracking-wide whitespace-nowrap text-ink-500 uppercase">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-100/80">
            {empty ? (
              <tr><td colSpan={head.length} className="px-5 py-14 text-center text-ink-400"><Inbox className="mx-auto mb-2 size-6" />Nothing here yet.</td></tr>
            ) : children}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Td({ children, className }: { children?: ReactNode; className?: string }) {
  return <td className={cn("px-5 py-4 align-top text-ink-700 transition-colors", className)}>{children}</td>;
}

export function Stars({ value, size = "sm" }: { value: number; size?: "sm" | "lg" }) {
  const s = size === "lg" ? "size-5" : "size-3.5";
  return (
    <span aria-label={`${value.toFixed(1)} out of 5`} className="inline-flex items-center gap-0.5 align-middle">
      {[1, 2, 3, 4, 5].map((n) => <Star key={n} className={cn(s, n <= Math.round(value) ? "fill-gold-400 text-gold-400" : "fill-ink-100 text-ink-100")} />)}
    </span>
  );
}

export function StarInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div role="radiogroup" aria-label="Rating" className="flex gap-1.5">
      {[1, 2, 3, 4, 5].map((n) => (
        <motion.button whileHover={{ scale: 1.15 }} whileTap={{ scale: 0.9 }} key={n} type="button" role="radio" aria-checked={value === n} aria-label={`${n} star${n > 1 ? "s" : ""}`} onClick={() => onChange(n)}>
          <Star className={cn("size-9 transition-colors", n <= value ? "fill-gold-400 text-gold-400" : "fill-ink-100 text-ink-200")} />
        </motion.button>
      ))}
    </div>
  );
}

export function Pagination({ page, count, pageSize = 25, onPage }: { page: number; count: number; pageSize?: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="mt-5 flex items-center justify-between text-sm text-ink-500">
      <span>Page <strong className="text-ink-800">{page}</strong> of {pages} · {count} total</span>
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" icon={ChevronLeft} disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
        <Button size="sm" variant="secondary" iconRight={ChevronRight} disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</Button>
      </div>
    </div>
  );
}

export function TierBadge({ tier }: { tier: string }) {
  if (tier === "elite") return <Badge tone="amber" className="bg-gradient-to-r from-gold-100 to-gold-50"><Star className="size-3 fill-current" /> Elite</Badge>;
  if (tier === "gold") return <Badge tone="amber">Gold tutor</Badge>;
  return <Badge tone="green"><CheckCircle2 className="size-3" /> Verified</Badge>;
}

export function Avatar({ name, src, size = 40, className }: { name: string; src?: string | null; size?: number; className?: string }) {
  const initials = name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
  const hue = [...name].reduce((a, c) => a + c.charCodeAt(0), 0) % 4;
  const bg = ["from-brand-400 to-brand-700", "from-gold-300 to-gold-500", "from-sky-400 to-brand-600", "from-violet-400 to-brand-600"][hue];
  return src ? (
    <img src={src} alt="" width={size} height={size} loading="lazy" className={cn("shrink-0 rounded-full object-cover ring-2 ring-white", className)} style={{ width: size, height: size }} />
  ) : (
    <span className={cn("inline-flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br font-display font-bold text-white ring-2 ring-white", bg, className)} style={{ width: size, height: size, fontSize: size * 0.38 }}>
      {initials}
    </span>
  );
}

/** Fade-and-rise when scrolled into view. */
export function Reveal({ children, delay = 0, className, y = 24 }: { children: ReactNode; delay?: number; className?: string; y?: number }) {
  return (
    <motion.div initial={{ opacity: 0, y }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-60px" }} transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }} className={className}>
      {children}
    </motion.div>
  );
}

/** Segmented tabs with an animated active pill. */
export function Tabs<T extends string>({ value, onChange, options, className }: { value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode }[]; className?: string }) {
  const id = useId();
  return (
    <div role="tablist" className={cn("inline-flex rounded-2xl bg-ink-100/70 p-1", className)}>
      {options.map((o) => (
        <button key={o.value} role="tab" type="button" aria-selected={value === o.value} onClick={() => onChange(o.value)}
          className={cn("relative min-h-10 flex-1 rounded-xl px-4 text-sm font-semibold transition-colors", value === o.value ? "text-ink-950" : "text-ink-500 hover:text-ink-700")}>
          {value === o.value && <motion.span layoutId={`tab-${id}`} className="absolute inset-0 rounded-xl bg-white shadow-soft" transition={{ type: "spring", stiffness: 500, damping: 35 }} />}
          <span className="relative">{o.label}</span>
        </button>
      ))}
    </div>
  );
}
