import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight, Banknote, Bell, BookOpen, CalendarDays, ChevronDown, ClipboardCheck, FileBarChart, Gavel, GraduationCap, Inbox, LayoutDashboard,
  ListChecks, LogOut, Mail, MapPin, Menu, MessageSquare, MessageSquareWarning, Phone, ScrollText, Search, Settings, ShieldCheck, Siren, Star,
  Tag, UserRound, Users, Video, Wallet, X, Baby, type LucideIcon,
} from "lucide-react";
import { AnimatePresence, motion } from "@/lib/motion";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { api } from "@/lib/api";
import { hasPerm, homeFor, useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import type { Me } from "@/lib/types";

import { Avatar, ButtonLink } from "./ui";

export function LogoMark({ className }: { className?: string }) {
  // Unique per instance: a gradient defined inside a hidden copy of the logo can't be referenced by a visible one.
  const gid = `tb-g-${useId().replace(/:/g, "")}`;
  return (
    <svg viewBox="0 0 40 40" className={cn("size-9", className)} aria-hidden="true">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#1d8a60" />
          <stop offset="1" stopColor="#082f22" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="12" fill={`url(#${gid})`} />
      <path d="M8 26c4.5-8.5 8.5-12.5 12-12.5S27.5 17.5 32 26" stroke="#fcbc4d" strokeWidth="3.4" fill="none" strokeLinecap="round" />
      <path d="M11 29h18" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
      <circle cx="20" cy="13.5" r="2.6" fill="#fff" />
    </svg>
  );
}

export function Logo({ className, light }: { className?: string; light?: boolean }) {
  return (
    <Link to="/" className={cn("flex items-center gap-2.5", className)} aria-label="TutorBridge home">
      <LogoMark />
      <span className={cn("font-display text-[1.3rem] font-bold tracking-tight", light ? "text-white" : "text-ink-950")}>
        Tutor<span className={light ? "text-gold-300" : "text-brand-600"}>Bridge</span>
      </span>
    </Link>
  );
}

const publicNav = [
  { to: "/tutors", label: "Find a tutor" },
  { to: "/how-it-works", label: "How it works" },
  { to: "/safety", label: "Safety" },
  { to: "/pricing", label: "Pricing" },
  { to: "/teach", label: "For tutors" },
];

/** Pages whose hero is dark, so the header starts transparent with light text. */
const DARK_HERO = ["/", "/teach", "/safety"];

function useScrolled(threshold = 24) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > threshold);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, [threshold]);
  return scrolled;
}

export function PublicLayout() {
  const { me } = useAuth();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const scrolled = useScrolled();
  const overDark = DARK_HERO.includes(pathname) && !scrolled && !open;
  useEffect(() => { setOpen(false); window.scrollTo({ top: 0 }); }, [pathname]);
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:rounded-lg focus:bg-white focus:p-3">Skip to content</a>
      <header className={cn("fixed inset-x-0 top-0 z-50 transition-all duration-300", overDark ? "bg-transparent" : "border-b border-ink-100/80 bg-cream/85 shadow-[0_1px_0_rgb(0_0_0/0.02)] backdrop-blur-xl")}>
        <div className="mx-auto flex h-[72px] max-w-7xl items-center justify-between px-4 sm:px-6">
          <Logo light={overDark} />
          <nav className="hidden items-center gap-1 lg:flex" aria-label="Main">
            {publicNav.map((n) => (
              <NavLink key={n.to} to={n.to} className={({ isActive }) => cn(
                "relative rounded-full px-4 py-2 text-[14.5px] font-medium transition-colors",
                overDark ? "text-white/80 hover:text-white" : "text-ink-600 hover:text-ink-950",
                isActive && (overDark ? "text-white" : "text-brand-700"),
              )}>
                {({ isActive }) => (<>
                  {n.label}
                  {isActive && <motion.span layoutId="nav-dot" className={cn("absolute -bottom-0.5 left-1/2 size-1 -translate-x-1/2 rounded-full", overDark ? "bg-gold-300" : "bg-brand-600")} />}
                </>)}
              </NavLink>
            ))}
          </nav>
          <div className="hidden items-center gap-2 lg:flex">
            {me ? (
              <ButtonLink to={homeFor(me)} variant={overDark ? "accent" : "primary"} iconRight={ArrowRight}>Dashboard</ButtonLink>
            ) : (
              <>
                <Link to="/login" className={cn("rounded-full px-4 py-2 text-[14.5px] font-semibold transition", overDark ? "text-white hover:bg-white/10" : "text-ink-700 hover:bg-ink-100/70")}>Log in</Link>
                <ButtonLink to="/signup?role=parent" variant={overDark ? "accent" : "primary"} iconRight={ArrowRight}>Find a tutor</ButtonLink>
              </>
            )}
          </div>
          <button className={cn("rounded-xl p-2.5 lg:hidden", overDark ? "text-white hover:bg-white/10" : "text-ink-800 hover:bg-ink-100")} aria-expanded={open} aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen((o) => !o)}>
            {open ? <X className="size-6" /> : <Menu className="size-6" />}
          </button>
        </div>
        <AnimatePresence>
          {open && (
            <motion.nav initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden border-t border-ink-100 bg-cream lg:hidden" aria-label="Mobile">
              <div className="space-y-1 px-4 py-4">
                {publicNav.map((n, i) => (
                  <motion.div key={n.to} initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}>
                    <Link to={n.to} className="block rounded-xl px-3 py-3 text-base font-semibold text-ink-800 hover:bg-white">{n.label}</Link>
                  </motion.div>
                ))}
                <div className="grid grid-cols-2 gap-2 pt-3">
                  {me ? <ButtonLink to={homeFor(me)} className="col-span-2">Go to dashboard</ButtonLink> : <>
                    <ButtonLink to="/login" variant="secondary">Log in</ButtonLink>
                    <ButtonLink to="/signup">Get started</ButtonLink>
                  </>}
                </div>
              </div>
            </motion.nav>
          )}
        </AnimatePresence>
      </header>
      <main id="main" className={cn("flex-1", !DARK_HERO.includes(pathname) && "pt-[72px]")}>
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}

function Footer() {
  const cols: [string, [string, string][]][] = [
    ["Parents", [["/tutors", "Find a tutor"], ["/how-it-works", "How it works"], ["/pricing", "Pricing"], ["/safety", "Safety standards"]]],
    ["Tutors", [["/teach", "Teach with us"], ["/signup?role=tutor", "Apply now"], ["/faq", "FAQ"], ["/blog", "Blog"]]],
    ["Company", [["/contact", "Contact"], ["/legal/terms", "Terms of service"], ["/legal/privacy", "Privacy policy"], ["/legal/refunds", "Refunds & cancellations"]]],
  ];
  return (
    <footer className="relative overflow-hidden bg-brand-950 text-brand-100">
      <div className="bg-grid pointer-events-none absolute inset-0 opacity-60" />
      <div className="absolute -top-40 left-1/2 h-80 w-[60rem] -translate-x-1/2 rounded-full bg-brand-600/20 blur-3xl" />
      <div className="relative mx-auto max-w-7xl px-4 pt-16 pb-8 sm:px-6">
        <div className="grid gap-12 lg:grid-cols-[1.3fr_2fr]">
          <div>
            <Logo light />
            <p className="mt-5 max-w-sm leading-relaxed text-brand-200/80">Vetted home tutors for Nigerian families. Every tutor checked, every lesson accounted for, every naira protected.</p>
            <div className="mt-6 space-y-2 text-sm text-brand-200/80">
              <p className="flex items-center gap-2"><MapPin className="size-4 text-gold-300" /> Lagos, Nigeria</p>
              <p className="flex items-center gap-2"><Mail className="size-4 text-gold-300" /> hello@tutorbridge.ng</p>
              <p className="flex items-center gap-2"><Phone className="size-4 text-gold-300" /> Emergencies: call 112, then use the in-app safety button</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-8 sm:grid-cols-3">
            {cols.map(([title, links]) => (
              <div key={title}>
                <p className="font-display text-sm font-semibold tracking-wide text-white">{title}</p>
                <ul className="mt-4 space-y-2.5 text-sm">
                  {links.map(([to, label]) => <li key={to}><Link to={to} className="text-brand-200/75 transition hover:text-gold-300">{label}</Link></li>)}
                </ul>
              </div>
            ))}
          </div>
        </div>
        <div className="mt-14 flex flex-col items-center justify-between gap-3 border-t border-white/10 pt-6 text-xs text-brand-200/60 sm:flex-row">
          <p>© {new Date().getFullYear()} TutorBridge. All rights reserved.</p>
          <p className="flex items-center gap-1.5"><ShieldCheck className="size-3.5 text-gold-300" /> Payments processed securely by Paystack · Card details never touch our servers</p>
        </div>
      </div>
    </footer>
  );
}

// --- Signed-in app shell ---------------------------------------------------

type NavItem = { to: string; label: string; icon: LucideIcon; show?: (me: Me) => boolean };
type NavGroup = { title?: string; items: NavItem[] };

const appNav: Record<"parent" | "tutor" | "staff", NavGroup[]> = {
  parent: [
    { items: [
      { to: "/parent", label: "Overview", icon: LayoutDashboard },
      { to: "/parent/requests", label: "Requests", icon: Search },
      { to: "/parent/bookings", label: "Bookings", icon: CalendarDays },
      { to: "/parent/children", label: "Children", icon: Baby },
    ] },
    { title: "Account", items: [
      { to: "/parent/wallet", label: "Wallet & payments", icon: Wallet },
      { to: "/messages", label: "Messages", icon: MessageSquare },
      { to: "/tutors", label: "Browse tutors", icon: GraduationCap },
    ] },
  ],
  tutor: [
    { items: [
      { to: "/tutor", label: "Overview", icon: LayoutDashboard },
      { to: "/tutor/onboarding", label: "Profile & vetting", icon: ClipboardCheck },
      { to: "/tutor/invitations", label: "Invitations", icon: Inbox },
    ] },
    { title: "Teaching", items: [
      { to: "/tutor/bookings", label: "Bookings", icon: CalendarDays },
      { to: "/tutor/lessons", label: "Lessons", icon: BookOpen },
      { to: "/tutor/earnings", label: "Earnings", icon: Banknote },
      { to: "/messages", label: "Messages", icon: MessageSquare },
    ] },
  ],
  staff: [
    { items: [{ to: "/staff", label: "Dashboard", icon: LayoutDashboard }] },
    { title: "Supply", items: [
      { to: "/staff/vetting", label: "Vetting queue", icon: ClipboardCheck, show: (m) => hasPerm(m, "vetting.view") },
      { to: "/staff/interviews", label: "Interviews", icon: Video, show: (m) => hasPerm(m, "vetting.review") },
      { to: "/staff/questions", label: "Question bank", icon: ListChecks, show: (m) => hasPerm(m, "vetting.review") },
    ] },
    { title: "Operations", items: [
      { to: "/staff/requests", label: "Requests", icon: Search, show: (m) => hasPerm(m, "requests.view") },
      { to: "/staff/bookings", label: "Bookings", icon: CalendarDays, show: (m) => hasPerm(m, "bookings.view") },
    ] },
    { title: "Money", items: [
      { to: "/staff/finance", label: "Finance", icon: FileBarChart, show: (m) => hasPerm(m, "finance.view") },
      { to: "/staff/payouts", label: "Payouts", icon: Banknote, show: (m) => hasPerm(m, "finance.view") },
      { to: "/staff/promos", label: "Promo codes", icon: Tag, show: (m) => hasPerm(m, "promos.manage") },
    ] },
    { title: "Trust & safety", items: [
      { to: "/staff/incidents", label: "Safety incidents", icon: Siren, show: (m) => hasPerm(m, "safety.view") },
      { to: "/staff/disputes", label: "Disputes", icon: Gavel, show: (m) => hasPerm(m, "disputes.view") },
      { to: "/staff/messages", label: "Flagged messages", icon: MessageSquareWarning, show: (m) => hasPerm(m, "messages.view") },
      { to: "/staff/reviews", label: "Reviews", icon: Star, show: (m) => hasPerm(m, "reviews.moderate") },
    ] },
    { title: "Admin", items: [
      { to: "/staff/users", label: "Users", icon: Users, show: (m) => hasPerm(m, "users.view") },
      { to: "/staff/settings", label: "Settings", icon: Settings, show: (m) => hasPerm(m, "users.view") },
      { to: "/staff/team", label: "Staff accounts", icon: ShieldCheck, show: (m) => hasPerm(m, "staff.manage") },
      { to: "/staff/audit", label: "Audit log", icon: ScrollText, show: (m) => hasPerm(m, "audit.view") },
    ] },
  ],
};

const ROLE_LABEL: Record<string, string> = {
  parent: "Parent", tutor: "Tutor", vetting_officer: "Vetting officer", ops_officer: "Operations", finance_officer: "Finance", safety_officer: "Safety officer", super_admin: "Super admin",
};

function NotificationBell() {
  const { data } = useQuery({ queryKey: ["notifications"], queryFn: () => api.get<{ unread: number }>("/notifications/"), refetchInterval: 60_000 });
  return (
    <Link to="/notifications" className="relative rounded-xl p-2.5 text-ink-500 transition hover:bg-ink-100 hover:text-ink-900" aria-label={`Notifications${data?.unread ? `, ${data.unread} unread` : ""}`}>
      <Bell className="size-5" />
      {!!data?.unread && (
        <span className="absolute top-1.5 right-1.5 flex min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] leading-4 font-bold text-white ring-2 ring-white">{data.unread > 9 ? "9+" : data.unread}</span>
      )}
    </Link>
  );
}

function UserMenu({ me }: { me: Me }) {
  const { logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="menu" className="flex items-center gap-2.5 rounded-2xl py-1.5 pr-2.5 pl-1.5 transition hover:bg-ink-100">
        <Avatar name={`${me.first_name} ${me.last_name}`} size={34} />
        <span className="hidden text-left sm:block">
          <span className="block text-sm leading-tight font-semibold text-ink-900">{me.first_name} {me.last_name}</span>
          <span className="block text-xs leading-tight text-ink-500">{ROLE_LABEL[me.role]}</span>
        </span>
        <ChevronDown className={cn("size-4 text-ink-400 transition-transform", open && "rotate-180")} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div role="menu" initial={{ opacity: 0, y: -6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6, scale: 0.97 }} transition={{ duration: 0.15 }}
            className="absolute right-0 z-50 mt-2 w-60 origin-top-right overflow-hidden rounded-2xl border border-ink-100 bg-white p-1.5 shadow-lift">
            <div className="px-3 py-2.5">
              <p className="truncate text-sm font-semibold text-ink-900">{me.email}</p>
              <p className="text-xs text-ink-500">{me.phone}</p>
            </div>
            <div className="my-1 h-px bg-ink-100" />
            <Link role="menuitem" to="/account" onClick={() => setOpen(false)} className="flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm text-ink-700 hover:bg-ink-50"><UserRound className="size-4" /> Account & security</Link>
            <Link role="menuitem" to="/notifications" onClick={() => setOpen(false)} className="flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm text-ink-700 hover:bg-ink-50"><Bell className="size-4" /> Notifications</Link>
            <Link role="menuitem" to="/" className="flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm text-ink-700 hover:bg-ink-50"><GraduationCap className="size-4" /> Public website</Link>
            <div className="my-1 h-px bg-ink-100" />
            <button role="menuitem" onClick={async () => { await logout(); nav("/"); }} className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-sm text-red-600 hover:bg-red-50"><LogOut className="size-4" /> Log out</button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function SideNav({ groups, me, onNavigate }: { groups: NavGroup[]; me: Me; onNavigate?: () => void }) {
  return (
    <nav className="space-y-6" aria-label="App">
      {groups.map((g, gi) => {
        const items = g.items.filter((i) => !i.show || i.show(me));
        if (!items.length) return null;
        return (
          <div key={gi}>
            {g.title && <p className="mb-2 px-3 text-[11px] font-semibold tracking-[0.12em] text-brand-200/50 uppercase">{g.title}</p>}
            <ul className="space-y-0.5">
              {items.map((i) => (
                <li key={i.to}>
                  <NavLink to={i.to} end={i.to.split("/").length <= 2} onClick={onNavigate}
                    className={({ isActive }) => cn("group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] font-medium transition-colors", isActive ? "text-white" : "text-brand-100/70 hover:bg-white/5 hover:text-white")}>
                    {({ isActive }) => (<>
                      {isActive && <motion.span layoutId="side-active" className="absolute inset-0 rounded-xl bg-gradient-to-r from-white/15 to-white/5 ring-1 ring-white/10" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
                      <i.icon className={cn("relative size-[18px]", isActive ? "text-gold-300" : "text-brand-200/60 group-hover:text-brand-100")} />
                      <span className="relative">{i.label}</span>
                    </>)}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

function SidebarShell({ children, me }: { children: ReactNode; me: Me }) {
  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-brand-950">
      <div className="bg-grid pointer-events-none absolute inset-0 opacity-40" />
      <div className="absolute -top-24 -left-24 size-64 rounded-full bg-brand-500/25 blur-3xl" />
      <div className="relative flex h-[72px] shrink-0 items-center px-5"><Logo light /></div>
      <div className="relative flex-1 overflow-y-auto px-3 pt-2 pb-6">{children}</div>
      {me.is_staff_member ? (
        <div className="relative m-3 rounded-2xl bg-white/5 p-3 text-xs text-brand-100/70 ring-1 ring-white/10">
          <p className="flex items-center gap-1.5 font-semibold text-white"><ShieldCheck className="size-3.5 text-gold-300" /> Staff console</p>
          <p className="mt-1">Every action here is audit-logged.</p>
        </div>
      ) : (
        <div className="relative m-3 rounded-2xl bg-gradient-to-br from-gold-300/20 to-transparent p-4 text-xs text-brand-100/80 ring-1 ring-gold-300/20">
          <p className="flex items-center gap-1.5 font-semibold text-white"><Siren className="size-3.5 text-gold-300" /> Safety first</p>
          <p className="mt-1 leading-relaxed">In an emergency call 112, then use the safety button on any lesson.</p>
        </div>
      )}
    </div>
  );
}

export function AppLayout({ area }: { area: "parent" | "tutor" | "staff" | "auto" }) {
  const { me } = useAuth();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [pathname]);
  if (!me) return null;
  const key = area === "auto" ? (me.role === "parent" ? "parent" : me.role === "tutor" ? "tutor" : "staff") : area;
  const groups = appNav[key];
  return (
    <div className="min-h-screen bg-cream">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[264px] lg:block">
        <SidebarShell me={me}><SideNav groups={groups} me={me} /></SidebarShell>
      </aside>
      <AnimatePresence>
        {open && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 bg-ink-950/50 backdrop-blur-sm" onClick={() => setOpen(false)} />
            <motion.aside initial={{ x: -300 }} animate={{ x: 0 }} exit={{ x: -300 }} transition={{ type: "spring", stiffness: 400, damping: 40 }} className="absolute inset-y-0 left-0 w-[280px] shadow-2xl">
              <SidebarShell me={me}><SideNav groups={groups} me={me} onNavigate={() => setOpen(false)} /></SidebarShell>
            </motion.aside>
          </div>
        )}
      </AnimatePresence>
      <div className="lg:pl-[264px]">
        <header className="sticky top-0 z-30 border-b border-ink-100/80 bg-cream/80 backdrop-blur-xl">
          <div className="flex h-[72px] items-center justify-between gap-3 px-4 sm:px-6 lg:px-10">
            <div className="flex items-center gap-2">
              <button className="rounded-xl p-2.5 text-ink-700 hover:bg-ink-100 lg:hidden" aria-label="Open menu" onClick={() => setOpen(true)}><Menu className="size-5" /></button>
              <span className="lg:hidden"><LogoMark className="size-8" /></span>
            </div>
            <div className="flex items-center gap-1.5">
              <NotificationBell />
              <UserMenu me={me} />
            </div>
          </div>
        </header>
        <main id="main" className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-10">
          {!me.is_verified && !me.is_staff_member && <VerifyBanner />}
          <motion.div key={pathname} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25, ease: "easeOut" }}>
            <Outlet />
          </motion.div>
        </main>
      </div>
    </div>
  );
}

function VerifyBanner() {
  return (
    <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
      className="mb-8 flex flex-col gap-3 rounded-3xl bg-gradient-to-r from-gold-100 via-gold-50 to-white p-5 ring-1 ring-gold-200 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-3">
        <span className="flex size-10 items-center justify-center rounded-2xl bg-gold-300 text-ink-950"><ShieldCheck className="size-5" /></span>
        <div>
          <p className="font-semibold text-ink-900">Verify your account</p>
          <p className="text-sm text-ink-600">Confirm your email and phone number before booking lessons or submitting your application.</p>
        </div>
      </div>
      <ButtonLink to="/verify" variant="dark" iconRight={ArrowRight}>Verify now</ButtonLink>
    </motion.div>
  );
}

export function Prose({ children }: { children: ReactNode }) {
  return <div className="prose-tb max-w-3xl text-[16.5px] text-ink-700">{children}</div>;
}
