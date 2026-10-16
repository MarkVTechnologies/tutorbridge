import {
  ArrowRight, Banknote, BookOpen, CalendarCheck, CalendarDays, Check, CheckCircle2, ClipboardCheck, Clock, Download, Hourglass, Inbox, KeyRound, LogIn, LogOut, MapPin,
  MessageSquare, Send, ShieldAlert, Sparkles, Star, Target, TrendingUp, Users, X,
} from "lucide-react";
import { motion } from "@/lib/motion";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { DateChip, greeting, LessonRow, QuickAction, WelcomeBanner } from "@/components/app";
import { Seo } from "@/components/Seo";
import {
  Alert, Avatar, Badge, Button, ButtonLink, Card, EmptyState, ErrorAlert, Input, Loading, Modal, PageHeader, Select, Stat, StatusBadge, Table, Tabs, Td, Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { dateOnly, dateTime, naira, relative, schedule as fmtSchedule, timeOnly, todayISO } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Booking, Lesson } from "@/lib/types";

import { LessonActions } from "../parent/LessonActions";
import { BankAccountCard } from "./Onboarding";

type Progress = { steps: { key: string; label: string; done: boolean }[]; completed: number; total: number; can_submit: boolean };
type OwnProfile = { status: string; status_display: string; progress: Progress; tier: string; rating_avg: string; rating_count: number; reliability_score: number; hours_taught: string; lessons_completed: number; strikes: number; background_valid_until: string | null };

export function TutorDashboard() {
  const { me } = useAuth();
  const profile = useApi<OwnProfile>("/tutor/profile/", ["tutor-profile"]);
  const offers = useApi<{ results: Booking[] }>("/bookings/?status=offered", ["bookings", "offered"]);
  const lessons = useApi<{ results: Lesson[] }>("/lessons/?upcoming=1", ["lessons", "upcoming"]);
  const earnings = useApi<{ pending_kobo: number; cleared_kobo: number; paid_kobo: number }>("/earnings/", ["earnings"]);
  const invites = useApi<unknown[]>("/tutor/invitations/", ["invitations"]);
  const p = profile.data;
  if (profile.isLoading || !p) return <Loading />;
  const active = p.status === "active";
  const upcoming = lessons.data?.results ?? [];
  const next = upcoming[0];
  return (
    <div>
      <Seo title="Overview" />
      <WelcomeBanner greeting={greeting()} title={`Hello, ${me?.first_name}`}
        subtitle={active ? (next ? <>Next lesson <strong className="text-white">{dateTime(next.scheduled_start)}</strong> with {next.child_name}</> : "You're live — families can find and book you.") : <>Application status: <span className="font-semibold text-gold-200">{p.status_display}</span></>}
        actions={active ? <>
          {next && <ButtonLink to={`/tutor/lessons/${next.id}`} variant="accent" icon={KeyRound}>{next.status === "in_progress" ? "Check out" : "Open next lesson"}</ButtonLink>}
          <ButtonLink to="/tutor/earnings" variant="outline-light" icon={Banknote}>Earnings</ButtonLink>
        </> : <ButtonLink to="/tutor/onboarding" variant="accent" iconRight={ArrowRight}>{p.status === "applied" ? "Continue application" : "View vetting progress"}</ButtonLink>}
        aside={active ? (
          <div className="grid grid-cols-2 gap-3">
            {[["Rating", Number(p.rating_avg) > 0 ? Number(p.rating_avg).toFixed(1) : "New", Star], ["Reliability", `${p.reliability_score}%`, Target], ["Hours", Math.round(Number(p.hours_taught)), Clock], ["Tier", p.tier, TrendingUp]].map(([l, v, I]) => {
              const Icon = I as typeof Star;
              return (
                <div key={l as string} className="rounded-2xl bg-white/10 p-4 ring-1 ring-white/15 backdrop-blur">
                  <Icon className="size-4 text-gold-300" />
                  <p className="mt-2 font-display text-2xl font-bold capitalize">{v as string}</p>
                  <p className="text-xs text-brand-100/70">{l as string}</p>
                </div>
              );
            })}
          </div>
        ) : <ApplicationProgress p={p} />} />

      {!!offers.data?.results.length && (
        <Card className="mb-6 border-gold-200 bg-gradient-to-br from-gold-50 to-white" title="New bookings — please respond" icon={Hourglass}>
          <div className="space-y-3">
            {offers.data.results.map((b) => (
              <div key={b.id} className="flex flex-wrap items-center gap-4 rounded-2xl bg-white p-4 ring-1 ring-gold-200">
                <Avatar name={b.child_name} size={44} />
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-ink-900">{b.child_name} ({b.child_class}) · {b.subject_names.join(", ")}</p>
                  <p className="text-sm text-ink-500">{fmtSchedule(b.schedule, b.lesson_minutes)} · {b.package_size} lesson{b.package_size > 1 ? "s" : ""} · {b.area_name}</p>
                </div>
                <Badge tone="amber"><Clock className="size-3" /> respond {relative(b.offer_expires_at)}</Badge>
                <ButtonLink to={`/tutor/bookings/${b.id}`} iconRight={ArrowRight}>Review</ButtonLink>
              </div>
            ))}
          </div>
        </Card>
      )}
      {!!invites.data?.length && (
        <Alert tone="blue" title={`${invites.data.length} new lesson request invitation${invites.data.length > 1 ? "s" : ""}`} className="mb-6">
          Our matching team thinks you'd be a great fit. <Link className="font-semibold underline" to="/tutor/invitations">Respond now →</Link>
        </Alert>
      )}
      {active && (
        <div className="mb-6 grid gap-4 sm:grid-cols-3">
          <Stat label="Cleared earnings" value={naira(earnings.data?.cleared_kobo)} hint="Paid in the next weekly run" tone="green" icon={Banknote} />
          <Stat label="Pending" value={naira(earnings.data?.pending_kobo)} hint="Delivered, inside the 48h window" icon={Hourglass} iconTone="gold" />
          <Stat label="Paid to date" value={naira(earnings.data?.paid_kobo)} hint={`${p.lessons_completed} lessons completed`} icon={CheckCircle2} iconTone="blue" />
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card title="Upcoming lessons" icon={CalendarDays} actions={<Link to="/tutor/lessons" className="text-sm font-semibold text-brand-600 hover:underline">All lessons</Link>}>
          {upcoming.length === 0 && <EmptyState icon={CalendarDays} title="No upcoming lessons">{active ? "New bookings will appear here once you accept them." : "Lessons appear here once you're approved and booked."}</EmptyState>}
          <div className="-mx-2.5 space-y-0.5">
            {upcoming.slice(0, 8).map((l) => <LessonRow key={l.id} lesson={l} to={`/tutor/lessons/${l.id}`} subtitle={l.child_name} />)}
          </div>
        </Card>
        <div className="space-y-3">
          <QuickAction to="/tutor/onboarding" icon={ClipboardCheck} title="Profile & vetting" body="Your subjects, areas, availability and checks" />
          <QuickAction to="/tutor/invitations" icon={Inbox} title="Invitations" body="Requests our team invited you to" />
          <QuickAction to="/messages" icon={MessageSquare} title="Messages" body="Chat with families you teach" />
          {p.strikes > 0 && <Alert tone="amber" title={`${p.strikes} strike${p.strikes > 1 ? "s" : ""} on your record`}>Three strikes trigger a review. Strikes come from no-shows and late cancellations.</Alert>}
        </div>
      </div>
    </div>
  );
}

function ApplicationProgress({ p }: { p: OwnProfile }) {
  const pct = Math.round((p.progress.completed / p.progress.total) * 100);
  const msgs: Record<string, string> = {
    applied: `${p.progress.completed} of ${p.progress.total} steps complete`,
    under_review: "Our vetting team is reviewing your documents and checks.",
    interview: "You're at the interview stage — make sure it's booked.",
    approved: "Approved! You'll go live once your police certificate is verified.",
    rejected: "Your application wasn't successful this time. Check your email.",
    suspended: "Your account is under review. Our safety team will contact you.",
  };
  return (
    <div className="rounded-3xl bg-white/10 p-5 ring-1 ring-white/15 backdrop-blur">
      <div className="flex items-baseline justify-between">
        <p className="text-sm font-semibold">Application</p>
        <p className="font-display text-3xl font-bold text-gold-300">{p.status === "applied" ? `${pct}%` : <ShieldAlert className="size-7" />}</p>
      </div>
      {p.status === "applied" && (
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/15">
          <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 1, ease: "easeOut" }} className="h-full rounded-full bg-gradient-to-r from-brand-300 to-gold-300" />
        </div>
      )}
      <p className="mt-3 text-sm text-brand-100/80">{msgs[p.status] ?? p.status_display}</p>
    </div>
  );
}

type Invitation = { id: number; status: string; subjects: string[]; level: string; class_name: string; area: string; schedule: { weekday: number; start: string }[]; lesson_minutes: number; start_date: string; goals: string; is_online: boolean; special_needs: boolean };

export function Invitations() {
  const { data, isLoading } = useApi<Invitation[]>("/tutor/invitations/", ["invitations"]);
  const [decline, setDecline] = useState<Invitation | null>(null);
  const [reason, setReason] = useState("");
  const respond = useAction((args: { id: number; accept: boolean }) => api.post(`/tutor/invitations/${args.id}/respond/`, { accept: args.accept, reason }), [["invitations"]], { success: "Response sent" });
  return (
    <div className="max-w-4xl">
      <Seo title="Invitations" />
      <PageHeader eyebrow="Opportunities" title="Lesson request invitations" subtitle="Our matching team thinks you'd be a great fit. Say you're interested and the family sees you on their shortlist." />
      {isLoading && <Loading />}
      {data?.length === 0 && <EmptyState icon={Inbox} title="No invitations right now">Keep your availability and areas up to date to get matched more often.</EmptyState>}
      <div className="space-y-4">
        {data?.map((i, idx) => (
          <Card key={i.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.05 }}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap gap-1.5">{i.subjects.map((s) => <Badge key={s} tone="green">{s}</Badge>)}<Badge>{i.class_name} · {i.level}</Badge>{i.special_needs && <Badge tone="blue">Extra support</Badge>}</div>
                <div className="mt-3 grid gap-2 text-sm text-ink-600 sm:grid-cols-3">
                  <span className="flex items-center gap-1.5"><MapPin className="size-4 text-ink-400" />{i.is_online ? "Online" : i.area}</span>
                  <span className="flex items-center gap-1.5"><Clock className="size-4 text-ink-400" />{fmtSchedule(i.schedule, i.lesson_minutes)}</span>
                  <span className="flex items-center gap-1.5"><CalendarDays className="size-4 text-ink-400" />From {dateOnly(i.start_date)}</span>
                </div>
                {i.goals && <p className="mt-3 rounded-2xl bg-ink-50/80 p-3 text-sm text-ink-700 italic">“{i.goals}”</p>}
              </div>
              {i.status === "invited" ? (
                <div className="flex gap-2">
                  <Button icon={Check} loading={respond.isPending} onClick={() => respond.mutate({ id: i.id, accept: true })}>I'm interested</Button>
                  <Button variant="secondary" icon={X} onClick={() => setDecline(i)}>Decline</Button>
                </div>
              ) : <StatusBadge status={i.status} />}
            </div>
          </Card>
        ))}
      </div>
      <Modal open={!!decline} onClose={() => setDecline(null)} title="Decline invitation" description="Your reason helps us match you better."
        footer={<Button loading={respond.isPending} disabled={!reason} onClick={() => respond.mutate({ id: decline!.id, accept: false }, { onSuccess: () => setDecline(null) })}>Decline</Button>}>
        <ErrorAlert error={respond.error} />
        <Select label="Reason" value={reason} onChange={(e) => setReason(e.target.value)}>
          <option value="">Choose…</option><option>Too far from me</option><option>Schedule doesn't work</option><option>Not my subject/level</option><option>Fully booked</option><option>Other</option>
        </Select>
      </Modal>
    </div>
  );
}

export function TutorBookings() {
  const { data, isLoading } = useApi<{ results: Booking[] }>("/bookings/", ["bookings"]);
  return (
    <div className="max-w-5xl">
      <Seo title="Bookings" />
      <PageHeader eyebrow="Teaching" title="Bookings" />
      {isLoading && <Loading />}
      {data?.results.length === 0 && <EmptyState icon={Users} title="No bookings yet">When a family books you, you'll be notified by SMS and it will appear here.</EmptyState>}
      <div className="grid gap-4 md:grid-cols-2">
        {data?.results.map((b) => (
          <Link key={b.id} to={`/tutor/bookings/${b.id}`} className="group rounded-3xl border border-ink-100 bg-white p-6 shadow-soft transition hover:border-brand-200 hover:shadow-lift">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <Avatar name={b.child_name} size={46} />
                <div><p className="font-display text-lg font-bold text-ink-950">{b.child_name}</p><p className="text-sm text-ink-500">{b.child_class} · {b.subject_names.join(", ")}</p></div>
              </div>
              <StatusBadge status={b.status} label={b.status_display} />
            </div>
            <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-600">
              <span className="flex items-center gap-1.5"><Clock className="size-4 text-ink-400" />{fmtSchedule(b.schedule, b.lesson_minutes)}</span>
              <span className="flex items-center gap-1.5"><MapPin className="size-4 text-ink-400" />{b.is_online ? "Online" : b.area_name}</span>
              <span className="flex items-center gap-1.5"><BookOpen className="size-4 text-ink-400" />{b.is_trial ? "Trial" : `${b.lessons_done}/${b.package_size} lessons`}</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function TutorBookingDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const key = ["booking", id];
  const { data: b, isLoading } = useApi<Booking>(`/bookings/${id}/`, key);
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const accept = useAction(() => api.post(`/bookings/${id}/accept/`), [key, ["bookings"]], { success: "Booking accepted — the family has been notified" });
  const decline = useAction(() => api.post(`/bookings/${id}/decline/`, { reason }), [["bookings"]], { success: "Booking declined" });
  if (isLoading) return <Loading />;
  if (!b) return <EmptyState title="Booking not found" />;
  return (
    <div className="max-w-5xl">
      <Seo title={`Booking · ${b.child_name}`} />
      <PageHeader back={{ to: "/tutor/bookings", label: "Bookings" }} eyebrow={b.subject_names.join(" · ")} title={`${b.child_name} (${b.child_class})`}
        actions={b.thread_id && <ButtonLink variant="secondary" to={`/messages/${b.thread_id}`} icon={MessageSquare}>Message parent</ButtonLink>} />
      {b.status === "offered" && (
        <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} className="mb-6 overflow-hidden rounded-3xl bg-gradient-to-br from-gold-100 via-gold-50 to-white p-6 ring-1 ring-gold-200">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="font-display text-xl font-bold text-ink-950">Accept this booking?</p>
              <p className="mt-1 text-sm text-ink-600">Payment is already secured. Respond by <strong>{dateTime(b.offer_expires_at)}</strong> or it's offered to another tutor.</p>
            </div>
            <div className="flex gap-2">
              <Button size="lg" icon={Check} loading={accept.isPending} onClick={() => accept.mutate()}>Accept</Button>
              <Button size="lg" variant="secondary" onClick={() => setDeclining(true)}>Decline</Button>
            </div>
          </div>
          <ErrorAlert error={accept.error} />
        </motion.div>
      )}
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <Card title="Lessons" icon={CalendarDays} className="self-start">
          {!b.accepted_at ? <p className="text-sm text-ink-500">Lessons and the family's address appear once you accept.</p> : (
            <ul className="space-y-3">
              {b.lessons?.map((l) => (
                <li key={l.id} className="rounded-2xl border border-ink-100 p-4">
                  <Link to={`/tutor/lessons/${l.id}`} className="flex items-center gap-4">
                    <DateChip iso={l.scheduled_start} />
                    <div className="flex-1"><p className="font-semibold text-ink-900">{timeOnly(l.scheduled_start)} – {timeOnly(l.scheduled_end)}</p>{l.note_topics && <p className="truncate text-sm text-ink-500">{l.note_topics}</p>}</div>
                    <StatusBadge status={l.status} label={l.status_display} />
                  </Link>
                  <LessonActions lesson={l} invalidate={[key]} />
                </li>
              ))}
            </ul>
          )}
        </Card>
        <div className="space-y-4">
          <Card>
            <dl className="space-y-3 text-sm">
              {[[Clock, "Schedule", fmtSchedule(b.schedule, b.lesson_minutes)], [BookOpen, "Package", b.is_trial ? "Trial lesson" : `${b.package_size} lessons`],
                [Banknote, "Your rate", `${naira(b.hourly_rate_kobo)}/hr · ${naira(b.lesson_price_kobo)} per lesson`],
                [MapPin, "Address", b.is_online ? "Online" : b.address_visible ?? `${b.area_name} — full address after you accept`]].map(([I, k, v]) => {
                const Icon = I as typeof Clock;
                return <div key={k as string} className="flex gap-3"><Icon className="mt-0.5 size-4 shrink-0 text-brand-500" /><div><dt className="text-xs text-ink-500">{k as string}</dt><dd className="font-medium text-ink-900">{v as string}</dd></div></div>;
              })}
            </dl>
          </Card>
          {b.parent_summary && (
            <Card title="Family record" subtitle="Shared so you can teach with confidence">
              <div className="grid grid-cols-2 gap-3 text-center">
                <div className="rounded-2xl bg-ink-50 p-3"><p className="font-display text-xl font-bold">{b.parent_summary.rating_avg ?? "—"}</p><p className="text-xs text-ink-500">Rating from tutors</p></div>
                <div className="rounded-2xl bg-ink-50 p-3"><p className="font-display text-xl font-bold">{b.parent_summary.cancellations}</p><p className="text-xs text-ink-500">Cancellations</p></div>
              </div>
            </Card>
          )}
        </div>
      </div>
      <Modal open={declining} onClose={() => setDeclining(false)} title="Decline booking" description="The family will be offered the next tutor on their shortlist."
        footer={<Button variant="danger" loading={decline.isPending} onClick={() => decline.mutate(undefined, { onSuccess: () => nav("/tutor/bookings") })}>Decline</Button>}>
        <ErrorAlert error={decline.error} />
        <Textarea label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Modal>
    </div>
  );
}

export function TutorLessons() {
  const [view, setView] = useState<"upcoming" | "all">("upcoming");
  const [from, setFrom] = useState(todayISO(-30));
  const path = view === "upcoming" ? "/lessons/?upcoming=1" : `/lessons/?from=${from}`;
  const { data, isLoading } = useApi<{ results: Lesson[]; count: number }>(path, ["lessons", view, from]);
  return (
    <div className="max-w-5xl">
      <Seo title="Lessons" />
      <PageHeader eyebrow="Teaching" title="Lessons" actions={<Tabs value={view} onChange={setView} options={[{ value: "upcoming", label: "Upcoming" }, { value: "all", label: "History" }]} />} />
      {view === "all" && <div className="mb-4 w-48"><Input label="From" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></div>}
      {isLoading && <Loading />}
      {data?.results.length === 0 && <EmptyState icon={CalendarDays} title="No lessons here" />}
      <Card className={cn(!data?.results.length && "hidden")}>
        <div className="-mx-2.5 space-y-0.5">
          {data?.results.map((l) => <LessonRow key={l.id} lesson={l} to={`/tutor/lessons/${l.id}`} subtitle={l.child_name} />)}
        </div>
      </Card>
    </div>
  );
}

/** LSN-02: mobile-first lesson page for check-in / check-out with codes and lesson note. */
export function LessonPage() {
  const { id } = useParams();
  const key = ["lesson", id];
  const { data: l, isLoading } = useApi<Lesson>(`/lessons/${id}/`, key);
  const profile = useApi<{ location_consent: boolean }>("/tutor/profile/", ["tutor-profile"]);
  const [code, setCode] = useState("");
  const [note, setNote] = useState({ topics: "", homework: "", observations: "" });
  const [locating, setLocating] = useState(false);
  const checkIn = useAction((pos: { lat?: number; lng?: number }) => api.post(`/lessons/${id}/check-in/`, { code, ...pos }), [key, ["lessons", "upcoming"]], { success: "Checked in — have a great lesson!" });
  const checkOut = useAction(() => api.post(`/lessons/${id}/check-out/`, { code, ...note }), [key, ["lessons", "upcoming"]], { success: "Checked out — lesson note sent to the parent" });
  if (isLoading) return <Loading />;
  if (!l) return <EmptyState title="Lesson not found" />;
  const doCheckIn = () => {
    const send = (pos: { lat?: number; lng?: number }) => checkIn.mutate(pos, { onSuccess: () => setCode("") });
    if (profile.data?.location_consent && "geolocation" in navigator) {
      setLocating(true);
      // The browser's permission prompt can sit unanswered forever (the API timeout only starts after
      // permission is granted), so fall back to checking in without location after 10 seconds.
      let done = false;
      const finish = (pos: { lat?: number; lng?: number }) => { if (done) return; done = true; setLocating(false); send(pos); };
      const fallback = window.setTimeout(() => finish({}), 10_000);
      navigator.geolocation.getCurrentPosition(
        (p) => { window.clearTimeout(fallback); finish({ lat: Number(p.coords.latitude.toFixed(6)), lng: Number(p.coords.longitude.toFixed(6)) }); },
        () => { window.clearTimeout(fallback); finish({}); },
        { timeout: 8000, maximumAge: 60000 },
      );
    } else send({});
  };
  const stage = l.status === "scheduled" ? 0 : l.status === "in_progress" ? 1 : 2;
  return (
    <div className="mx-auto max-w-md">
      <Seo title={`Lesson · ${l.child_name}`} />
      <Link to="/tutor/lessons" className="mb-4 inline-flex items-center gap-1 text-sm font-medium text-ink-500 hover:text-brand-700">← Lessons</Link>
      <div className="grain relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-brand-700 to-brand-950 p-6 text-white shadow-lift">
        <div className="bg-grid pointer-events-none absolute inset-0 opacity-50" />
        <div className="relative flex items-center gap-4">
          <DateChip iso={l.scheduled_start} tone="dark" />
          <div>
            <p className="font-display text-2xl font-bold">{l.child_name}</p>
            <p className="text-sm text-brand-100/80">{timeOnly(l.scheduled_start)} – {timeOnly(l.scheduled_end)}</p>
          </div>
        </div>
        <div className="relative mt-6 flex items-center gap-2">
          {[["Check in", LogIn], ["Teach", BookOpen], ["Check out", LogOut]].map(([t, I], i) => {
            const Icon = I as typeof LogIn;
            return (
              <div key={t as string} className="flex flex-1 items-center gap-2">
                <span className={cn("flex size-9 items-center justify-center rounded-full ring-1 transition", i < stage ? "bg-gold-300 text-ink-950 ring-gold-300" : i === stage ? "bg-white text-brand-800 ring-white" : "bg-white/5 text-white/50 ring-white/15")}>
                  {i < stage ? <Check className="size-4" strokeWidth={3} /> : <Icon className="size-4" />}
                </span>
                <span className={cn("text-xs font-semibold", i <= stage ? "text-white" : "text-white/50")}>{t as string}</span>
              </div>
            );
          })}
        </div>
      </div>

      {l.status === "scheduled" && (
        <Card className="mt-4">
          <p className="font-display text-lg font-bold">Arrived? Check in.</p>
          <p className="mt-1 text-sm text-ink-500">Ask the parent for today's 6-digit check-in code.</p>
          <form className="mt-5 space-y-4" onSubmit={(e) => { e.preventDefault(); doCheckIn(); }}>
            <ErrorAlert error={checkIn.error} />
            <CodeInput value={code} onChange={setCode} label="Check-in code" />
            <Button type="submit" size="lg" className="w-full" icon={LogIn} loading={checkIn.isPending || locating} disabled={code.length !== 6}>Check in</Button>
          </form>
        </Card>
      )}
      {l.status === "in_progress" && (
        <Card className="mt-4">
          <p className="font-display text-lg font-bold">Finish the lesson</p>
          <p className="mt-1 text-sm text-ink-500">Checked in at {timeOnly(l.checkin_at)}. Write your note, then ask for the check-out code.</p>
          <form className="mt-5 space-y-4" onSubmit={(e) => { e.preventDefault(); checkOut.mutate(undefined, { onSuccess: () => setCode("") }); }}>
            <ErrorAlert error={checkOut.error} />
            <Textarea label="Topics covered" required value={note.topics} onChange={(e) => setNote({ ...note, topics: e.target.value })} />
            <Textarea label="Homework set" value={note.homework} onChange={(e) => setNote({ ...note, homework: e.target.value })} />
            <Textarea label="Observations for the parent" value={note.observations} onChange={(e) => setNote({ ...note, observations: e.target.value })} />
            <CodeInput value={code} onChange={setCode} label="Check-out code" />
            <Button type="submit" size="lg" className="w-full" icon={LogOut} loading={checkOut.isPending} disabled={code.length !== 6 || !note.topics.trim()}>Check out</Button>
          </form>
        </Card>
      )}
      {["completed", "confirmed"].includes(l.status) && (
        <Card className="mt-4" title="Lesson note" icon={CheckCircle2}>
          <div className="space-y-2 text-sm">
            <p><span className="font-semibold">Covered:</span> {l.note_topics}</p>
            {l.note_homework && <p><span className="font-semibold">Homework:</span> {l.note_homework}</p>}
            {l.note_observations && <p><span className="font-semibold">Notes:</span> {l.note_observations}</p>}
          </div>
          <Alert tone={l.status === "confirmed" ? "green" : "blue"} className="mt-4">{l.status === "confirmed" ? "Confirmed — this lesson's earnings are cleared." : "Payment clears when the parent confirms, or automatically after 48 hours."}</Alert>
        </Card>
      )}
      <div className="mt-2"><LessonActions lesson={l} invalidate={[key]} /></div>
    </div>
  );
}

/** Six large digit boxes backed by one input (works with numeric keypads and paste). */
function CodeInput({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <label className="relative block">
      <span className="sr-only">{label}</span>
      <input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={value} onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 6))}
        className="peer absolute inset-0 z-10 opacity-0" aria-label={label} />
      <div className="flex justify-between gap-2" aria-hidden="true">
        {Array.from({ length: 6 }).map((_, i) => (
          <span key={i} className={cn("flex h-16 flex-1 items-center justify-center rounded-2xl bg-white font-display text-3xl font-bold ring-2 transition",
            i === value.length ? "ring-brand-500 peer-focus:ring-brand-500" : value[i] ? "ring-ink-300" : "ring-ink-200")}>
            {value[i] ?? ""}
          </span>
        ))}
      </div>
    </label>
  );
}

type Earnings = {
  pending_kobo: number; cleared_kobo: number; in_transit_kobo: number; paid_kobo: number;
  lessons: { id: number; date: string; child: string; status: string; escrow_status: string; net_kobo: number }[];
  payouts: { date: string; amount_kobo: number; status: string; bank: string }[];
};

export function TutorEarnings() {
  const { data, isLoading } = useApi<Earnings>("/earnings/", ["earnings"]);
  const [month, setMonth] = useState(todayISO().slice(0, 7));
  if (isLoading) return <Loading />;
  return (
    <div className="max-w-6xl">
      <Seo title="Earnings" />
      <PageHeader eyebrow="Money" title="Earnings" subtitle="Confirmed lessons are paid every week to your verified bank account." />
      <div className="grain relative mb-6 overflow-hidden rounded-[2rem] bg-gradient-to-br from-ink-900 via-brand-950 to-brand-900 p-7 text-white shadow-lift">
        <div className="bg-grid pointer-events-none absolute inset-0 opacity-40" />
        <div className="relative grid gap-6 sm:grid-cols-4">
          {[["Cleared — next payout", data?.cleared_kobo, true], ["Pending (48h window)", data?.pending_kobo], ["On the way", data?.in_transit_kobo], ["Paid to date", data?.paid_kobo]].map(([l, v, big]) => (
            <div key={l as string}>
              <p className="text-xs text-brand-100/70">{l as string}</p>
              <p className={cn("mt-1 font-display font-bold", big ? "text-4xl text-gold-300" : "text-2xl")}>{naira(v as number)}</p>
            </div>
          ))}
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <BankAccountCard />
        <Card title="Monthly statement" icon={Download} subtitle="PDF for your records">
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-48"><Input label="Month" type="month" value={month} onChange={(e) => setMonth(e.target.value)} /></div>
            <a className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white shadow-glow hover:bg-brand-700" href={`/api/earnings/statement/?month=${month}`}><Download className="size-4" />Download PDF</a>
          </div>
        </Card>
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <div>
          <h2 className="mb-3 flex items-center gap-2 font-display text-lg font-semibold"><Send className="size-4 text-brand-500" />Payouts</h2>
          <Table head={["Date", "Amount", "Bank", "Status"]} empty={!data?.payouts.length}>
            {data?.payouts.map((p, i) => <tr key={i}><Td>{dateOnly(p.date)}</Td><Td className="font-semibold">{naira(p.amount_kobo)}</Td><Td className="text-xs">{p.bank}</Td><Td><StatusBadge status={p.status} /></Td></tr>)}
          </Table>
        </div>
        <div>
          <h2 className="mb-3 flex items-center gap-2 font-display text-lg font-semibold"><CalendarCheck className="size-4 text-brand-500" />By lesson</h2>
          <Table head={["Date", "Student", "Payment", "You earn"]} empty={!data?.lessons.length}>
            {data?.lessons.map((l) => <tr key={l.id}><Td>{dateOnly(l.date)}</Td><Td>{l.child}</Td><Td><StatusBadge status={l.escrow_status} /></Td><Td className="font-semibold">{naira(l.net_kobo)}</Td></tr>)}
          </Table>
        </div>
      </div>
      <p className="mt-6 flex items-center gap-2 text-sm text-ink-500"><Sparkles className="size-4 text-gold-500" />Commission falls as you reach Gold and Elite tiers through hours, ratings and reliability.</p>
    </div>
  );
}
