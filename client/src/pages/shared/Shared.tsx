import {
  ArrowLeft, ArrowRight, Banknote, Bell, BellOff, CalendarCheck, CheckCheck, CheckCircle2, Clock, CreditCard, Download, KeyRound, Lock, Mail, MessageSquare,
  MessageSquareLock, Send, ShieldCheck, Siren, Smartphone, Sparkles, XCircle, type LucideIcon,
} from "lucide-react";
import { AnimatePresence, motion } from "@/lib/motion";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "react-toastify";

import { Seo } from "@/components/Seo";
import { Alert, Avatar, Badge, Button, ButtonLink, Card, Checkbox, EmptyState, ErrorAlert, IconTile, Input, Loading, PageHeader, Spinner, type TileTone } from "@/components/ui";
import { api } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { naira, relative, timeOnly } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Me, Notification } from "@/lib/types";

// --- Account ------------------------------------------------------------------

export function Account() {
  const { me, setMe } = useAuth();
  const [prefs, setPrefs] = useState<Record<string, boolean>>({});
  const [code, setCode] = useState("");
  useEffect(() => { if (me) setPrefs({ email: true, sms: true, inapp: true, ...me.notification_prefs }); }, [me]);
  const save = useAction((body: Record<string, unknown>) => api.patch<Me>("/auth/me/", body), [], { success: "Preferences saved" });
  const disable2fa = useAction(() => api.post<Me>("/auth/2fa/disable/", { code }), [], { success: "Two-factor turned off" });
  if (!me) return <Loading />;
  const download = async () => {
    const data = await api.get("/auth/me/export/");
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "tutorbridge-my-data.json";
    a.click();
    toast.success("Your data export has downloaded");
  };
  return (
    <div className="max-w-4xl">
      <Seo title="Account" />
      <PageHeader eyebrow="Settings" title="Account & security" />
      <Card className="mb-6">
        <div className="flex flex-wrap items-center gap-5">
          <Avatar name={`${me.first_name} ${me.last_name}`} size={72} />
          <div className="flex-1">
            <p className="font-display text-2xl font-bold text-ink-950">{me.first_name} {me.last_name}</p>
            <div className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-500">
              <span className="flex items-center gap-1.5"><Mail className="size-4" />{me.email} {me.email_verified_at && <CheckCircle2 className="size-4 text-brand-500" />}</span>
              <span className="flex items-center gap-1.5"><Smartphone className="size-4" />{me.phone} {me.phone_verified_at && <CheckCircle2 className="size-4 text-brand-500" />}</span>
            </div>
          </div>
          {me.is_verified ? <Badge tone="green"><ShieldCheck className="size-3.5" /> Verified account</Badge> : <ButtonLink to="/verify" variant="accent" size="sm">Verify account</ButtonLink>}
        </div>
      </Card>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Notifications" icon={Bell} subtitle="How we reach you">
          <div className="space-y-4">
            {([["email", "Email", Mail], ["sms", "SMS — bookings, reminders, codes, payouts", Smartphone], ["inapp", "In-app", Bell]] as const).map(([k, l, I]) => (
              <div key={k} className="flex items-center justify-between gap-3 rounded-2xl bg-ink-50/70 px-4 py-3">
                <span className="flex items-center gap-3 text-sm font-medium text-ink-800"><I className="size-4 text-ink-500" />{l}</span>
                <Toggle checked={prefs[k] !== false} onChange={(v) => setPrefs({ ...prefs, [k]: v })} label={l} />
              </div>
            ))}
            <p className="text-xs text-ink-500">Security messages (codes, password resets, account locks) are always sent.</p>
            <Checkbox label="Send me study tips and offers" checked={me.consent_marketing} onChange={(e) => save.mutate({ consent_marketing: e.target.checked }, { onSuccess: (m) => setMe(m as Me) })} />
            <Button loading={save.isPending} onClick={() => save.mutate({ notification_prefs: prefs }, { onSuccess: (m) => setMe(m as Me) })}>Save preferences</Button>
          </div>
        </Card>
        <div className="space-y-6">
          <Card title="Two-factor authentication" icon={Lock} subtitle="An authenticator code at every sign-in">
            {me.totp_enabled ? (
              <div className="space-y-4">
                <Alert tone="green">Two-factor authentication is on.</Alert>
                {!me.is_staff_member && (
                  <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); disable2fa.mutate(undefined, { onSuccess: (m) => setMe(m as Me) }); }}>
                    <div className="w-40"><Input label="Code to turn off" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} /></div>
                    <Button variant="secondary" loading={disable2fa.isPending}>Turn off</Button>
                  </form>
                )}
                <ErrorAlert error={disable2fa.error} />
              </div>
            ) : (
              <div className="space-y-4">
                <p className="text-sm text-ink-600">Protect your account and payments with a code from Google Authenticator or a similar app.</p>
                <ButtonLink to="/account/2fa" icon={ShieldCheck}>Set up two-factor</ButtonLink>
              </div>
            )}
          </Card>
          <Card title="Your data" icon={Download} subtitle="Nigeria Data Protection Act rights">
            <p className="text-sm leading-relaxed text-ink-600">Download a copy of the personal data we hold about you. To correct or delete your account, contact us — financial records are kept as the law requires.</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="secondary" icon={Download} onClick={download}>Download my data</Button>
              <ButtonLink to="/contact" variant="ghost">Request deletion</ButtonLink>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)}
      className={cn("relative h-7 w-12 shrink-0 rounded-full transition-colors", checked ? "bg-brand-600" : "bg-ink-200")}>
      <motion.span layout transition={{ type: "spring", stiffness: 600, damping: 35 }} className={cn("absolute top-1 size-5 rounded-full bg-white shadow", checked ? "right-1" : "left-1")} />
    </button>
  );
}

// --- Notifications ------------------------------------------------------------

const EVENT_ICON: Record<string, [LucideIcon, TileTone]> = {
  payment_received: [CreditCard, "green"], booking_confirmed: [CalendarCheck, "green"], booking_offer: [CalendarCheck, "gold"], shortlist_ready: [Sparkles, "gold"],
  tutor_checked_in: [KeyRound, "green"], tutor_checked_out: [CheckCheck, "green"], tutor_late: [Clock, "red"], no_show: [XCircle, "red"], payout_sent: [Banknote, "green"],
  new_message: [MessageSquare, "blue"], safety_alert: [Siren, "red"], dispute_update: [ShieldCheck, "violet"], lesson_reminder: [Bell, "blue"], lesson_reminder_tutor: [Bell, "blue"],
};

export function Notifications() {
  const { data, isLoading } = useApi<{ unread: number; items: Notification[] }>("/notifications/", ["notifications"]);
  const markRead = useAction(() => api.post("/notifications/read/"), [["notifications"]]);
  const marked = useRef(false);
  useEffect(() => {
    if (data?.unread && !marked.current) { marked.current = true; markRead.mutate(); }
  }, [data?.unread, markRead]);
  return (
    <div className="max-w-3xl">
      <Seo title="Notifications" />
      <PageHeader eyebrow="Inbox" title="Notifications" />
      {isLoading && <Loading />}
      {data?.items.length === 0 && <EmptyState icon={BellOff} title="You're all caught up">Booking updates, check-ins and payouts will appear here.</EmptyState>}
      <ul className="space-y-2.5">
        {data?.items.map((n, i) => {
          const [Icon, tone] = EVENT_ICON[n.event] ?? [Bell, "ink" as TileTone];
          const body = (
            <div className={cn("flex gap-4 rounded-3xl border bg-white p-4 shadow-soft transition", !n.read ? "border-brand-200" : "border-ink-100", n.link && "hover:border-brand-200 hover:shadow-lift")}>
              <IconTile icon={Icon} tone={tone} />
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-3">
                  <p className="font-semibold text-ink-900">{n.subject || n.body}</p>
                  <span className="shrink-0 text-xs text-ink-400">{relative(n.created_at)}</span>
                </div>
                {n.subject && <p className="mt-0.5 text-sm text-ink-600">{n.body}</p>}
              </div>
              {!n.read && <span className="mt-2 size-2 shrink-0 rounded-full bg-brand-500" />}
            </div>
          );
          return (
            <motion.li key={n.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 10) * 0.03 }}>
              {n.link ? <Link to={n.link}>{body}</Link> : body}
            </motion.li>
          );
        })}
      </ul>
    </div>
  );
}

// --- Messages -----------------------------------------------------------------

type ThreadRow = { id: number; booking: number; with: string; child: string; last_message: string; last_at: string; unread: number };
type Msg = { id: number; mine: boolean; sender: string; body: string; masked: boolean; created_at: string };

export function Messages() {
  const { id } = useParams();
  const { data: threads, isLoading } = useApi<ThreadRow[]>("/threads/", ["threads"]);
  const active = threads?.find((t) => String(t.id) === id);
  return (
    <div>
      <Seo title="Messages" />
      <PageHeader eyebrow="Inbox" title="Messages" subtitle={<span className="flex items-center gap-1.5"><MessageSquareLock className="size-4 text-brand-500" />Phone numbers, emails and links are hidden automatically to keep everyone protected.</span>} />
      <div className="grid h-[calc(100vh-15rem)] min-h-[520px] overflow-hidden rounded-3xl border border-ink-100 bg-white shadow-soft md:grid-cols-[20rem_1fr]">
        <aside className={cn("flex flex-col border-r border-ink-100", id && "hidden md:flex")}>
          <div className="border-b border-ink-100 px-5 py-4 text-sm font-semibold text-ink-500">Conversations</div>
          <div className="flex-1 overflow-y-auto p-2">
            {isLoading && <Loading />}
            {threads?.length === 0 && <p className="p-6 text-center text-sm text-ink-500">Messaging opens once a tutor accepts a booking.</p>}
            {threads?.map((t) => (
              <Link key={t.id} to={`/messages/${t.id}`} className={cn("flex items-center gap-3 rounded-2xl p-3 transition", String(t.id) === id ? "bg-brand-50" : "hover:bg-ink-50")}>
                <Avatar name={t.with} size={44} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate font-semibold text-ink-900">{t.with}</p>
                    <span className="shrink-0 text-[11px] text-ink-400">{relative(t.last_at)}</span>
                  </div>
                  <p className="truncate text-sm text-ink-500">{t.last_message || `Lessons for ${t.child}`}</p>
                </div>
                {t.unread > 0 && <span className="flex size-5 items-center justify-center rounded-full bg-brand-600 text-[11px] font-bold text-white">{t.unread}</span>}
              </Link>
            ))}
          </div>
        </aside>
        {id ? <Thread id={id} title={active?.with ?? ""} child={active?.child ?? ""} /> : (
          <div className="hidden items-center justify-center md:flex"><EmptyState icon={MessageSquare} title="Select a conversation">Pick a conversation on the left to start chatting.</EmptyState></div>
        )}
      </div>
    </div>
  );
}

function Thread({ id, title, child }: { id: string; title: string; child: string }) {
  const { data, isLoading } = useThreadMessages(id);
  const [body, setBody] = useState("");
  const send = useAction(() => api.post(`/threads/${id}/messages/`, { body }), [["thread", id], ["threads"]]);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [data?.length]);
  return (
    <section className="flex min-h-0 flex-col">
      <header className="flex items-center gap-3 border-b border-ink-100 px-5 py-3.5">
        <Link to="/messages" className="rounded-lg p-1 text-ink-500 md:hidden" aria-label="All conversations"><ArrowLeft className="size-5" /></Link>
        {title && <Avatar name={title} size={38} />}
        <div><p className="font-semibold text-ink-900">{title}</p>{child && <p className="text-xs text-ink-500">Lessons for {child}</p>}</div>
      </header>
      <div className="flex-1 space-y-3 overflow-y-auto bg-[radial-gradient(var(--color-ink-100)_1px,transparent_1px)] bg-[size:20px_20px] p-5">
        {isLoading && <Loading />}
        {data?.length === 0 && <p className="py-10 text-center text-sm text-ink-500">Say hello 👋</p>}
        <AnimatePresence initial={false}>
          {data?.map((m) => (
            <motion.div key={m.id} initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} className={cn("flex", m.mine ? "justify-end" : "justify-start")}>
              <div className={cn("max-w-[78%] rounded-3xl px-4 py-2.5 text-[15px] shadow-soft", m.mine ? "rounded-br-lg bg-brand-600 text-white" : "rounded-bl-lg bg-white text-ink-800 ring-1 ring-ink-100")}>
                <p className="whitespace-pre-wrap">{m.body}</p>
                <p className={cn("mt-1 flex items-center gap-1 text-[11px]", m.mine ? "text-brand-100" : "text-ink-400")}>
                  {timeOnly(m.created_at)}{m.masked && <><Lock className="size-3" /> details hidden</>}
                </p>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        <div ref={end} />
      </div>
      {send.error && <div className="px-4 pt-3"><ErrorAlert error={send.error} /></div>}
      <form className="flex items-center gap-2 border-t border-ink-100 p-3" onSubmit={(e) => { e.preventDefault(); if (body.trim()) send.mutate(undefined, { onSuccess: () => setBody("") }); }}>
        <label htmlFor="msg" className="sr-only">Message</label>
        <input id="msg" className="input rounded-full" placeholder="Write a message…" value={body} maxLength={2000} onChange={(e) => setBody(e.target.value)} />
        <Button type="submit" loading={send.isPending} className="size-11 rounded-full p-0" aria-label="Send">{!send.isPending && <Send className="size-4" />}</Button>
      </form>
    </section>
  );
}

function useThreadMessages(id: string) {
  return useApi<Msg[]>(`/threads/${id}/messages/`, ["thread", id]);
}

// --- Payments -----------------------------------------------------------------

/** Return page after the gateway's hosted checkout. Status comes from the server (credited only by verified webhook). */
export function PaymentCallback() {
  const [params] = useSearchParams();
  const ref = params.get("reference") || params.get("trxref") || params.get("tx_ref");
  const { me } = useAuth();
  const [status, setStatus] = useState<string>("initiated");
  const [tries, setTries] = useState(0);
  useEffect(() => {
    if (!ref || status === "success" || status === "failed" || tries > 20) return;
    const t = setTimeout(async () => {
      try {
        const p = await api.get<{ status: string }>(`/payments/${ref}/`);
        setStatus(p.status);
      } finally {
        setTries((n) => n + 1);
      }
    }, tries === 0 ? 0 : 3000);
    return () => clearTimeout(t);
  }, [ref, status, tries]);
  const ok = status === "success";
  const failed = status === "failed";
  const waiting = !ok && !failed;
  return (
    <div className="flex min-h-[70vh] items-center justify-center px-4 py-16">
      <Seo title="Payment" />
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-lg rounded-[2rem] border border-ink-100 bg-white p-8 text-center shadow-lift sm:p-10">
        <div className="mx-auto flex size-20 items-center justify-center">
          {waiting && tries <= 20 && <Spinner className="size-12" />}
          {ok && (
            <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 300, damping: 15 }} className="flex size-20 items-center justify-center rounded-full bg-brand-500 text-white shadow-glow">
              <motion.svg viewBox="0 0 24 24" className="size-10" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <motion.path d="M5 12.5l4.5 4.5L19 7.5" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ delay: 0.25, duration: 0.45 }} />
              </motion.svg>
            </motion.div>
          )}
          {failed && <div className="flex size-20 items-center justify-center rounded-full bg-red-100 text-red-600"><XCircle className="size-10" /></div>}
        </div>
        <h1 className="mt-6 font-display text-3xl font-bold text-ink-950">{ok ? "Payment received" : failed ? "Payment not completed" : tries > 20 ? "Still confirming" : "Confirming your payment"}</h1>
        <p className="mx-auto mt-2 max-w-sm text-ink-500">
          {ok ? "Your money is held safely by TutorBridge and your booking has gone to the tutor." : failed ? "You haven't been charged. Please try again." : tries > 20 ? "We're waiting for the payment provider. We'll notify you the moment it arrives." : "Checking with the payment provider — this takes a few seconds."}
        </p>
        {ok && (
          <ol className="mt-8 space-y-3 rounded-3xl bg-ink-50/80 p-5 text-left text-sm">
            {[["The tutor accepts within 12 hours", CalendarCheck], ["You'll get an SMS with lesson details", Smartphone], ["Lesson-day codes appear on your dashboard", KeyRound]].map(([t, I], i) => {
              const Icon = I as LucideIcon;
              return (
                <motion.li key={t as string} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.5 + i * 0.1 }} className="flex items-center gap-3">
                  <span className="flex size-8 items-center justify-center rounded-xl bg-white text-brand-600 shadow-soft"><Icon className="size-4" /></span>{t as string}
                </motion.li>
              );
            })}
          </ol>
        )}
        <ButtonLink to={me ? homeFor(me) : "/"} size="lg" className="mt-8 w-full" iconRight={ArrowRight}>Go to dashboard</ButtonLink>
      </motion.div>
    </div>
  );
}

/** DEV ONLY: stands in for the gateway's hosted checkout when PAYMENT_GATEWAY=fake. */
export function FakeCheckout() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const ref = params.get("reference")!;
  const pay = useAction(() => api.post("/payments/dev/fake-complete/", { reference: ref }));
  return (
    <div className="flex min-h-[70vh] items-center justify-center px-4 py-16">
      <Card className="w-full max-w-md">
        <Badge tone="amber">Development only</Badge>
        <h1 className="mt-4 font-display text-2xl font-bold">Test checkout</h1>
        <p className="mt-1 text-sm text-ink-500">Stands in for Paystack's hosted checkout. In production parents are redirected to the real gateway.</p>
        <p className="mt-6 font-display text-4xl font-bold">{naira(Number(params.get("amount")))}</p>
        <p className="font-mono text-xs text-ink-400">{ref}</p>
        <ErrorAlert error={pay.error} />
        <div className="mt-6 flex gap-2">
          <Button size="lg" className="flex-1" icon={CreditCard} loading={pay.isPending} onClick={() => pay.mutate(undefined, { onSuccess: () => nav(`/payments/callback?reference=${ref}`) })}>Pay now (test)</Button>
          <Button size="lg" variant="secondary" onClick={() => nav(-1)}>Cancel</Button>
        </div>
      </Card>
    </div>
  );
}

