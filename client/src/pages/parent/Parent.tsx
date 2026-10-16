import {
  ArrowRight, Baby, CalendarDays, CalendarPlus, Download, GraduationCap, MapPin, MessageSquare, Pencil, Plus, Receipt, RefreshCw, Search, Sparkles,
  Star, UserRoundPlus, Wallet as WalletIcon, Clock, Target, Banknote, Globe, CreditCard, Tag,
} from "lucide-react";
import { motion } from "@/lib/motion";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { CodeDisplay, DateChip, greeting, LessonRow, QuickAction, StatusStepper, WelcomeBanner } from "@/components/app";
import { CalendarButton } from "@/components/CalendarButton";
import { ReferralCard } from "@/components/ReferralCard";
import { Seo } from "@/components/Seo";
import { KeyValue, ScheduleEditor, TutorCard } from "@/components/shared";
import {
  Alert, Avatar, Badge, Button, ButtonLink, Card, Checkbox, EmptyState, ErrorAlert, Input, Loading, Modal, PageHeader, Select, StarInput, Stat, StatusBadge, Table, Td, Textarea,
} from "@/components/ui";
import { api, type ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { dateOnly, dateTime, naira, schedule as fmtSchedule, timeOnly, toKobo, todayISO } from "@/lib/format";
import { useAction, useApi, useRefData } from "@/lib/hooks";
import type { Booking, Child, Lesson, LessonRequest, Slot, TutorPublic, WalletData } from "@/lib/types";

import { LessonActions } from "./LessonActions";

const REQUEST_STEPS = [
  { key: "submitted", label: "Submitted" },
  { key: "matching", label: "Matching" },
  { key: "shortlist_ready", label: "Shortlist ready" },
  { key: "booked", label: "Booked" },
];

export function ParentDashboard() {
  const { me } = useAuth();
  const lessons = useApi<{ results: Lesson[] }>("/lessons/?upcoming=1", ["lessons", "upcoming"]);
  const requests = useApi<{ results: LessonRequest[] }>("/requests/", ["requests"]);
  const wallet = useApi<{ balance_kobo: number; in_escrow_kobo: number }>("/wallet/", ["wallet"]);
  const children = useApi<Child[]>("/parent/children/", ["children"]);
  const openReqs = requests.data?.results.filter((r) => !["booked", "closed"].includes(r.status)) ?? [];
  const upcoming = lessons.data?.results ?? [];
  const next = upcoming[0];
  const today = upcoming.filter((l) => l.codes);
  return (
    <div>
      <Seo title="Overview" />
      <WelcomeBanner greeting={greeting()} title={`Welcome back, ${me?.first_name}`}
        subtitle={next ? <>Next lesson: <strong className="text-white">{dateTime(next.scheduled_start)}</strong> — {next.child_name} with {next.tutor_name}</> : "Every lesson is checked in, noted and protected by escrow."}
        actions={<>
          <ButtonLink to="/parent/requests/new" variant="accent" icon={Plus}>Request a tutor</ButtonLink>
          <ButtonLink to="/tutors" variant="outline-light" icon={Search}>Browse tutors</ButtonLink>
        </>}
        aside={today[0]?.codes ? (
          <div className="rounded-3xl bg-white/10 p-5 ring-1 ring-white/15 backdrop-blur">
            <p className="text-sm font-semibold">Today · {timeOnly(today[0].scheduled_start)} · {today[0].child_name}</p>
            <div className="mt-3 space-y-3">
              {today[0].codes.checkin && <CodeDisplay dark label="Check-in code" code={today[0].codes.checkin} />}
              <CodeDisplay dark label="Check-out code" code={today[0].codes.checkout} />
            </div>
            <p className="mt-3 text-xs text-brand-100/70">Share only in person, when the tutor arrives and when the lesson ends.</p>
          </div>
        ) : undefined} />

      {children.data?.length === 0 && (
        <Alert tone="amber" title="Start by adding your child" className="mb-6">We need their class and curriculum to match the right tutor. <Link className="font-semibold underline" to="/parent/children">Add a child →</Link></Alert>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Wallet balance" value={naira(wallet.data?.balance_kobo)} hint="Available for bookings" icon={WalletIcon} />
        <Stat label="Held for lessons" value={naira(wallet.data?.in_escrow_kobo)} hint="Released only after each lesson is confirmed" icon={Banknote} iconTone="gold" />
        <Stat label="Open requests" value={openReqs.length} hint={openReqs.length ? "We'll notify you when your shortlist is ready" : "No requests in progress"} icon={Search} iconTone="blue" />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card title="Upcoming lessons" icon={CalendarDays} actions={<Link to="/parent/bookings" className="text-sm font-semibold text-brand-600 hover:underline">All bookings</Link>}>
          {lessons.isLoading && <Loading />}
          {!lessons.isLoading && upcoming.length === 0 && (
            <EmptyState icon={CalendarPlus} title="No lessons scheduled" action={<ButtonLink to="/parent/requests/new" size="sm" icon={Plus}>Request a tutor</ButtonLink>}>Book a trial from your shortlist and lessons will appear here.</EmptyState>
          )}
          <div className="-mx-2.5 space-y-0.5">
            {upcoming.slice(0, 6).map((l) => <LessonRow key={l.id} lesson={l} to={`/parent/bookings/${l.booking}`} subtitle={`${l.child_name} with ${l.tutor_name}`} />)}
          </div>
        </Card>
        <div className="space-y-6">
          {openReqs.length > 0 && (
            <Card title="Requests in progress" icon={Sparkles}>
              <div className="space-y-4">
                {openReqs.map((r) => (
                  <Link key={r.id} to={`/parent/requests/${r.id}`} className="block rounded-2xl border border-ink-100 p-4 transition hover:border-brand-200 hover:bg-brand-50/30">
                    <div className="mb-3 flex items-center justify-between gap-2">
                      <p className="font-semibold text-ink-900">{r.subject_names.join(", ")} · {r.child_name}</p>
                      <ArrowRight className="size-4 text-ink-400" />
                    </div>
                    <StatusStepper steps={REQUEST_STEPS} current={r.status} />
                  </Link>
                ))}
              </div>
            </Card>
          )}
          <div className="space-y-3">
            <QuickAction to="/parent/children" icon={Baby} title="Your children" body="Profiles, classes and learning notes" />
            <QuickAction to="/parent/wallet" icon={Receipt} title="Payments & receipts" body="Top up, download receipts, see wallet activity" />
            <QuickAction to="/messages" icon={MessageSquare} title="Messages" body="Chat with your tutors, safely" />
            <ReferralCard audience="parent" />
          </div>
        </div>
      </div>
    </div>
  );
}

// --- Children -------------------------------------------------------------

export function Children() {
  const { data, isLoading } = useApi<Child[]>("/parent/children/", ["children"]);
  const [editing, setEditing] = useState<Partial<Child> | null>(null);
  return (
    <div className="max-w-5xl">
      <Seo title="Children" />
      <PageHeader eyebrow="Family" title="Children" subtitle="We only store what's needed to match a tutor: first name, class and learning needs."
        actions={<Button icon={UserRoundPlus} onClick={() => setEditing({})}>Add a child</Button>} />
      {isLoading && <Loading />}
      {data?.length === 0 && <EmptyState icon={Baby} title="No children added yet" action={<Button icon={Plus} onClick={() => setEditing({})}>Add your first child</Button>}>Add a child to start requesting tutors.</EmptyState>}
      <div className="grid gap-5 sm:grid-cols-2">
        {data?.map((c, i) => (
          <Card key={c.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
            <div className="flex items-start gap-4">
              <Avatar name={c.first_name} size={56} />
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <h2 className="font-display text-xl font-bold text-ink-950">{c.first_name}</h2>
                  <Button size="sm" variant="ghost" icon={Pencil} onClick={() => setEditing(c)}>Edit</Button>
                </div>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  <Badge tone="green">{c.class_name}</Badge>
                  <Badge>{c.level_name}</Badge>
                  <Badge>{c.curriculum_name}</Badge>
                  {c.special_needs && <Badge tone="blue">Extra support</Badge>}
                </div>
                {c.learning_notes && <p className="mt-3 rounded-2xl bg-ink-50/80 p-3 text-sm leading-relaxed text-ink-600">{c.learning_notes}</p>}
                <ButtonLink to="/parent/requests/new" size="sm" variant="secondary" className="mt-4" iconRight={ArrowRight}>Request a tutor for {c.first_name}</ButtonLink>
              </div>
            </div>
          </Card>
        ))}
      </div>
      {editing && <ChildForm child={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function ChildForm({ child, onClose }: { child: Partial<Child>; onClose: () => void }) {
  const { data: ref } = useRefData();
  const [f, setF] = useState({ first_name: child.first_name ?? "", class_name: child.class_name ?? "", level: child.level ?? "", curriculum: child.curriculum ?? "", school_type: child.school_type ?? "", learning_notes: child.learning_notes ?? "", special_needs: child.special_needs ?? false, parental_consent: !!child.id });
  const save = useAction(() => (child.id ? api.patch(`/parent/children/${child.id}/`, f) : api.post("/parent/children/", f)), [["children"]], { success: child.id ? "Saved" : "Child added" });
  return (
    <Modal open onClose={onClose} title={child.id ? `Edit ${child.first_name}` : "Add a child"} description="Learning notes are stored encrypted and shared only with your matched tutor."
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate(undefined, { onSuccess: onClose })}>Save</Button></>}>
      <ErrorAlert error={save.error} />
      <Input label="First name" value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} error={save.error?.field("first_name")} />
      <div className="grid grid-cols-2 gap-3">
        <Input label="Class" placeholder="e.g. JSS2, Year 9" value={f.class_name} onChange={(e) => setF({ ...f, class_name: e.target.value })} />
        <Select label="Level" value={f.level} onChange={(e) => setF({ ...f, level: Number(e.target.value) })}>
          <option value="">Choose…</option>{ref?.levels.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </Select>
        <Select label="Curriculum" value={f.curriculum} onChange={(e) => setF({ ...f, curriculum: Number(e.target.value) })}>
          <option value="">Choose…</option>{ref?.curricula.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
        <Select label="School type" value={f.school_type} onChange={(e) => setF({ ...f, school_type: e.target.value })}>
          <option value="">—</option><option value="private">Private</option><option value="public">Public</option><option value="international">International</option><option value="homeschool">Home-school</option>
        </Select>
      </div>
      <Textarea label="Learning notes (optional)" hint="Strengths, struggles, anything the tutor should know." value={f.learning_notes} onChange={(e) => setF({ ...f, learning_notes: e.target.value })} />
      <Checkbox label="My child needs extra learning support" checked={f.special_needs} onChange={(e) => setF({ ...f, special_needs: e.target.checked })} />
      {!child.id && <Checkbox label="I am this child's parent or guardian and consent to TutorBridge storing this information." checked={f.parental_consent} onChange={(e) => setF({ ...f, parental_consent: e.target.checked })} />}
    </Modal>
  );
}

// --- Requests -------------------------------------------------------------

export function Requests() {
  const { data, isLoading } = useApi<{ results: LessonRequest[] }>("/requests/", ["requests"]);
  return (
    <div className="max-w-5xl">
      <Seo title="Requests" />
      <PageHeader eyebrow="Matching" title="Lesson requests" subtitle="Each request gets a hand-checked shortlist within 24 hours." actions={<ButtonLink to="/parent/requests/new" icon={Plus}>New request</ButtonLink>} />
      {isLoading && <Loading />}
      {data?.results.length === 0 && <EmptyState icon={Search} title="No requests yet" action={<ButtonLink to="/parent/requests/new" icon={Plus}>Request a tutor</ButtonLink>}>Tell us what your child needs and we'll do the searching.</EmptyState>}
      <div className="space-y-4">
        {data?.results.map((r, i) => (
          <motion.div key={r.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
            <Link to={`/parent/requests/${r.id}`} className="group block rounded-3xl border border-ink-100 bg-white p-6 shadow-soft transition hover:border-brand-200 hover:shadow-lift">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-display text-lg font-bold text-ink-950">{r.subject_names.join(", ")} <span className="font-sans text-base font-normal text-ink-500">for {r.child_name}</span></p>
                  <p className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-500">
                    <span className="flex items-center gap-1.5"><Clock className="size-3.5" />{fmtSchedule(r.schedule, r.lesson_minutes)}</span>
                    <span className="flex items-center gap-1.5"><MapPin className="size-3.5" />{r.is_online ? "Online" : r.area_name}</span>
                    <span className="flex items-center gap-1.5"><CalendarDays className="size-3.5" />Created {dateOnly(r.created_at)}</span>
                  </p>
                </div>
                <StatusBadge status={r.status} label={r.status_display} />
              </div>
              {r.status !== "closed" && <div className="mt-5"><StatusStepper steps={REQUEST_STEPS} current={r.status} /></div>}
            </Link>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

export function NewRequest() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { data: ref } = useRefData();
  const children = useApi<Child[]>("/parent/children/", ["children"]);
  const profile = useApi<{ address: string; area: number | null }>("/parent/profile/", ["parent-profile"]);
  const requestedTutor = params.get("tutor");
  const tutor = useApi<TutorPublic>(requestedTutor ? `/tutors/${requestedTutor}/` : null);
  const [f, setF] = useState({
    child: "", subjects: [] as number[], goals: "", schedule: [] as Slot[], lesson_minutes: 90, start_date: todayISO(3),
    address: "", area: "", budget_max: "", gender: "", is_online: false,
  });
  useEffect(() => {
    if (profile.data) setF((x) => ({ ...x, address: x.address || profile.data!.address || "", area: x.area || String(profile.data!.area ?? "") }));
  }, [profile.data]);
  useEffect(() => {
    if (children.data?.length === 1) setF((x) => ({ ...x, child: x.child || String(children.data![0].id) }));
  }, [children.data]);
  const submit = useAction(() => api.post<LessonRequest>("/requests/", {
    child: Number(f.child), subjects: f.subjects, goals: f.goals, schedule: f.schedule, lesson_minutes: f.lesson_minutes, start_date: f.start_date,
    address: f.address, area: Number(f.area), budget_max_kobo: f.budget_max ? toKobo(f.budget_max) : 0, is_online: f.is_online,
    preferences: f.gender ? { gender: f.gender } : {}, requested_tutor: requestedTutor ? Number(requestedTutor) : null,
  }), [["requests"]], { success: "Request submitted — we're matching tutors now" });
  const e = submit.error;
  if (children.data?.length === 0) return <EmptyState icon={Baby} title="Add your child first" action={<ButtonLink to="/parent/children" icon={UserRoundPlus}>Add a child</ButtonLink>}>We need your child's class and curriculum to find the right tutor.</EmptyState>;
  const section = (n: number, title: string, icon: React.ReactNode, children: React.ReactNode) => (
    <Card>
      <div className="mb-5 flex items-center gap-3">
        <span className="flex size-9 items-center justify-center rounded-xl bg-brand-600 font-display text-sm font-bold text-white">{n}</span>
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold text-ink-950">{title} {icon}</h2>
      </div>
      <div className="space-y-5">{children}</div>
    </Card>
  );
  return (
    <div className="max-w-3xl">
      <Seo title="Request a tutor" />
      <PageHeader eyebrow="New request" title="Request a tutor" subtitle="Tell us what you need. We'll send a shortlist of vetted tutors within 24 hours." back={{ to: "/parent/requests", label: "Requests" }} />
      {tutor.data && <Alert tone="blue" className="mb-5">You're requesting <strong>{tutor.data.name}</strong>. We'll check their availability and include similar tutors in case they can't take you.</Alert>}
      <form className="space-y-5" onSubmit={(ev) => { ev.preventDefault(); submit.mutate(undefined, { onSuccess: (r) => nav(`/parent/requests/${r.id}`) }); }}>
        {e && <ErrorAlert error={e} />}
        {section(1, "Who and what", <GraduationCap className="size-4 text-brand-500" />, <>
          <div>
            <p className="mb-2 text-[13px] font-semibold text-ink-700">Child</p>
            <div className="flex flex-wrap gap-2">
              {children.data?.map((c) => (
                <button type="button" key={c.id} onClick={() => setF({ ...f, child: String(c.id) })} aria-pressed={f.child === String(c.id)}
                  className={cn("flex items-center gap-2.5 rounded-2xl border-2 py-2 pr-4 pl-2 text-left transition", f.child === String(c.id) ? "border-brand-500 bg-brand-50" : "border-ink-100 bg-white hover:border-ink-200")}>
                  <Avatar name={c.first_name} size={34} />
                  <span><span className="block text-sm font-semibold">{c.first_name}</span><span className="block text-xs text-ink-500">{c.class_name}</span></span>
                </button>
              ))}
            </div>
            {e?.field("child") && <p className="mt-1 text-sm text-red-600">{e.field("child")}</p>}
          </div>
          <fieldset>
            <legend className="mb-2 text-[13px] font-semibold text-ink-700">Subjects</legend>
            <div className="flex flex-wrap gap-2">
              {ref?.subjects.map((s) => {
                const on = f.subjects.includes(s.id);
                return <motion.button whileTap={{ scale: 0.95 }} type="button" key={s.id} aria-pressed={on} onClick={() => setF({ ...f, subjects: on ? f.subjects.filter((x) => x !== s.id) : [...f.subjects, s.id] })}
                  className={cn("rounded-full px-3.5 py-1.5 text-sm font-medium ring-1 transition", on ? "bg-brand-600 text-white ring-brand-600" : "bg-white text-ink-700 ring-ink-200 hover:ring-ink-300")}>{s.name}</motion.button>;
              })}
            </div>
            {e?.field("subjects") && <p className="mt-1 text-sm text-red-600">{e.field("subjects")}</p>}
          </fieldset>
          <Textarea label="Goals" placeholder="e.g. Prepare for Common Entrance in May; build confidence in algebra" value={f.goals} onChange={(ev) => setF({ ...f, goals: ev.target.value })} />
        </>)}
        {section(2, "When", <Clock className="size-4 text-brand-500" />, <>
          <ScheduleEditor value={f.schedule} onChange={(schedule) => setF({ ...f, schedule })} />
          {e?.field("schedule") && <p className="text-sm text-red-600">{e.field("schedule")}</p>}
          <div className="grid gap-3 sm:grid-cols-2">
            <Select label="Lesson length" value={f.lesson_minutes} onChange={(ev) => setF({ ...f, lesson_minutes: Number(ev.target.value) })}>
              {ref?.config.lesson_durations_minutes.map((m) => <option key={m} value={m}>{m / 60} hour{m > 60 ? "s" : ""}</option>)}
            </Select>
            <Input label="Start date" type="date" min={todayISO()} value={f.start_date} onChange={(ev) => setF({ ...f, start_date: ev.target.value })} error={e?.field("start_date")} />
          </div>
        </>)}
        {section(3, "Where and budget", <MapPin className="size-4 text-brand-500" />, <>
          <div className="grid gap-3 sm:grid-cols-2">
            {[[false, "At home", MapPin], [true, "Online", Globe]].map(([v, l, I]) => {
              const Icon = I as typeof MapPin;
              return (
                <button type="button" key={String(v)} onClick={() => setF({ ...f, is_online: v as boolean })} aria-pressed={f.is_online === v}
                  className={cn("flex items-center gap-3 rounded-2xl border-2 p-4 text-left transition", f.is_online === v ? "border-brand-500 bg-brand-50" : "border-ink-100 bg-white hover:border-ink-200")}>
                  <Icon className="size-5 text-brand-600" /><span className="font-semibold">{l as string}</span>
                </button>
              );
            })}
          </div>
          <Select label="Area" required value={f.area} onChange={(ev) => setF({ ...f, area: ev.target.value })} error={e?.field("area")}>
            <option value="">Choose…</option>{ref?.areas.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </Select>
          {!f.is_online && <Input label="Lesson address" icon={MapPin} hint="Shared with the tutor only after they accept your booking." value={f.address} onChange={(ev) => setF({ ...f, address: ev.target.value })} error={e?.field("address")} />}
          <div className="grid gap-3 sm:grid-cols-2">
            <Input label="Maximum budget per hour (₦)" icon={Banknote} inputMode="numeric" placeholder="e.g. 8000" value={f.budget_max} onChange={(ev) => setF({ ...f, budget_max: ev.target.value })} />
            <Select label="Tutor gender preference" value={f.gender} onChange={(ev) => setF({ ...f, gender: ev.target.value })}>
              <option value="">No preference</option><option value="female">Female tutor only</option><option value="male">Male tutor only</option>
            </Select>
          </div>
        </>)}
        <div className="flex items-center justify-between gap-4 rounded-3xl bg-brand-950 p-5 text-white">
          <p className="text-sm text-brand-100/80">Free to submit. You only pay when you book.</p>
          <Button type="submit" variant="accent" size="lg" loading={submit.isPending} iconRight={ArrowRight}>Submit request</Button>
        </div>
      </form>
    </div>
  );
}

export function RequestDetail() {
  const { id } = useParams();
  const req = useApi<LessonRequest>(`/requests/${id}/`, ["request", id]);
  const shortlist = useApi<{ published: boolean; items: { id: number; tutor: TutorPublic; rank: number; status: string }[] }>(`/requests/${id}/shortlist/`, ["shortlist", id]);
  const [booking, setBooking] = useState<TutorPublic | null>(null);
  const close = useAction(() => api.post(`/requests/${id}/close/`), [["request", id], ["requests"]], { success: "Request closed" });
  if (req.isLoading) return <Loading />;
  const r = req.data;
  if (!r) return null;
  return (
    <div className="max-w-5xl">
      <Seo title="Your shortlist" />
      <PageHeader eyebrow={`Request for ${r.child_name}`} title={r.subject_names.join(", ")} back={{ to: "/parent/requests", label: "Requests" }}
        actions={!["booked", "closed"].includes(r.status) && <Button variant="secondary" loading={close.isPending} onClick={() => close.mutate()}>Close request</Button>} />
      <Card className="mb-8">
        <StatusStepper steps={REQUEST_STEPS} current={r.status} />
        <div className="mt-6 border-t border-ink-100 pt-5">
          <KeyValue items={[["Schedule", fmtSchedule(r.schedule, r.lesson_minutes)], ["Start", dateOnly(r.start_date)], ["Where", r.is_online ? "Online" : r.area_name], ["Budget", r.budget_max_kobo ? `Up to ${naira(r.budget_max_kobo)}/hour` : "Flexible"]]} />
        </div>
      </Card>
      <h2 className="mb-4 font-display text-2xl font-bold text-ink-950">Your shortlist</h2>
      {shortlist.isLoading && <Loading />}
      {shortlist.data && !shortlist.data.published && (
        <div className="relative overflow-hidden rounded-3xl border border-ink-100 bg-white p-10 text-center shadow-soft">
          <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 8, ease: "linear" }} className="mx-auto flex size-16 items-center justify-center rounded-full bg-gradient-to-br from-brand-100 to-gold-100">
            <Sparkles className="size-7 text-brand-600" />
          </motion.div>
          <p className="mt-5 font-display text-xl font-bold text-ink-950">We're hand-picking your tutors</p>
          <p className="mx-auto mt-2 max-w-md text-ink-500">Our matching team is reviewing tutors for subject fit, distance, schedule and reviews. You'll get an SMS and email the moment your shortlist is ready — usually within 24 hours.</p>
        </div>
      )}
      <div className="space-y-4">
        {shortlist.data?.items.map((m, i) => (
          <motion.div key={m.id} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }}>
            <TutorCard tutor={m.tutor} highlight={m.rank === 1} action={r.status !== "closed" && <Button onClick={() => setBooking(m.tutor)} iconRight={ArrowRight}>Book</Button>} />
          </motion.div>
        ))}
      </div>
      {booking && <BookModal tutor={booking} request={r} onClose={() => setBooking(null)} />}
    </div>
  );
}

type Quote = { lesson_price_kobo: number; package_size: number; lessons_total_kobo: number; matching_fee_kobo: number; matching_credit_kobo: number; discount_kobo: number; promo_code: string | null; total_kobo: number; wallet_balance_kobo: number };

function BookModal({ tutor, request, onClose }: { tutor: TutorPublic; request: LessonRequest; onClose: () => void }) {
  const { data: ref } = useRefData();
  const nav = useNavigate();
  const [pkg, setPkg] = useState(1);
  const [minutes, setMinutes] = useState(request.lesson_minutes);
  const [slots, setSlots] = useState<Slot[]>(request.schedule);
  const [start, setStart] = useState(request.start_date < todayISO(1) ? todayISO(1) : request.start_date);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [promoInput, setPromoInput] = useState("");
  const [promo, setPromo] = useState("");
  const [promoError, setPromoError] = useState<string | null>(null);
  useEffect(() => {
    api.post<Quote>("/bookings-quote/", { tutor: tutor.id, package_size: pkg, lesson_minutes: minutes, request: request.id, promo_code: promo || undefined })
      .then((q) => { setQuote(q); if (promo) setPromoError(null); })
      .catch((e: ApiError) => {
        if (promo && e.field?.("promo_code")) { setPromoError(e.field("promo_code") ?? null); setPromo(""); } else setQuote(null);
      });
  }, [tutor.id, pkg, minutes, request.id, promo]);
  const book = useAction(() => api.post<{ booking: Booking; payment: { authorization_url: string } | null }>("/bookings/book/", {
    tutor: tutor.id, child: request.child, subjects: request.subjects, package_size: pkg, lesson_minutes: minutes, schedule: slots, start_date: start, request: request.id,
    promo_code: promo || undefined,
  }), [["wallet"], ["shortlist", String(request.id)]]);
  const due = quote ? Math.max(0, quote.total_kobo - quote.wallet_balance_kobo) : 0;
  const subjectsTaught = useMemo(() => new Set(tutor.subjects.map((s) => s.subject_name)), [tutor]);
  const missing = request.subject_names.filter((s) => !subjectsTaught.has(s));
  return (
    <Modal open onClose={onClose} title={`Book ${tutor.name}`} description="Payment is held in escrow and released lesson by lesson."
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button loading={book.isPending} disabled={!slots.length} icon={WalletIcon} onClick={() => book.mutate(undefined, {
          onSuccess: (r) => { if (r.payment) window.location.href = r.payment.authorization_url; else nav(`/parent/bookings/${r.booking.id}`); },
        })}>{due > 0 ? `Pay ${naira(due)}` : "Book with wallet balance"}</Button></>}>
      {missing.length > 0 && <Alert tone="amber">This tutor doesn't list {missing.join(", ")} at your child's level.</Alert>}
      <ErrorAlert error={book.error} />
      <div>
        <p className="mb-2 text-[13px] font-semibold text-ink-700">What would you like to book?</p>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
          {ref?.config.package_sizes.map((n) => (
            <button key={n} type="button" onClick={() => setPkg(n)} aria-pressed={pkg === n}
              className={cn("rounded-2xl border-2 px-2 py-3 text-center transition", pkg === n ? "border-brand-500 bg-brand-50" : "border-ink-100 hover:border-ink-200")}>
              <span className="block font-display text-lg font-bold">{n}</span>
              <span className="block text-[11px] text-ink-500">{n === 1 ? "Trial" : "lessons"}</span>
            </button>
          ))}
        </div>
      </div>
      <Select label="Lesson length" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
        {ref?.config.lesson_durations_minutes.map((m) => <option key={m} value={m}>{m / 60} hour{m > 60 ? "s" : ""}</option>)}
      </Select>
      <div><p className="mb-2 text-[13px] font-semibold text-ink-700">Weekly schedule</p><ScheduleEditor value={slots} onChange={setSlots} /></div>
      <Input label="First lesson on or after" type="date" min={todayISO(1)} value={start} onChange={(e) => setStart(e.target.value)} />
      <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); setPromo(promoInput.trim()); }}>
        <div className="flex-1"><Input label="Promo code (optional)" icon={Tag} value={promoInput} onChange={(e) => { setPromoInput(e.target.value.toUpperCase()); setPromoError(null); }} error={promoError ?? undefined} /></div>
        {quote?.promo_code ? <Button type="button" variant="ghost" onClick={() => { setPromo(""); setPromoInput(""); }}>Remove</Button> : <Button type="submit" variant="secondary" disabled={!promoInput.trim()}>Apply</Button>}
      </form>
      {quote && (
        <div className="rounded-2xl bg-ink-50/80 p-4 text-sm">
          <div className="flex justify-between py-1"><span className="text-ink-600">{quote.package_size} × {naira(quote.lesson_price_kobo)}</span><span>{naira(quote.lessons_total_kobo)}</span></div>
          {quote.matching_fee_kobo > 0 && <div className="flex justify-between py-1"><span className="text-ink-600">Matching fee <span className="text-ink-400">(credited on your first package)</span></span><span>{naira(quote.matching_fee_kobo)}</span></div>}
          {quote.matching_credit_kobo > 0 && <div className="flex justify-between py-1 text-brand-700"><span>Matching fee credit</span><span>−{naira(quote.matching_credit_kobo)}</span></div>}
          {quote.discount_kobo > 0 && <div className="flex justify-between py-1 text-brand-700"><span>Promo {quote.promo_code}</span><span>−{naira(quote.discount_kobo)}</span></div>}
          {quote.wallet_balance_kobo > 0 && <div className="flex justify-between py-1 text-brand-700"><span>From your wallet</span><span>−{naira(Math.min(quote.wallet_balance_kobo, quote.total_kobo))}</span></div>}
          <div className="mt-2 flex justify-between border-t border-ink-200 pt-3 font-display text-lg font-bold"><span>To pay now</span><span>{naira(due)}</span></div>
        </div>
      )}
      <p className="text-xs leading-relaxed text-ink-500">The tutor has {ref?.config.booking_accept_hours ?? 12} hours to accept, or we offer your booking to the next tutor on your shortlist.</p>
    </Modal>
  );
}

// --- Bookings -------------------------------------------------------------

export function ParentBookings() {
  const { data, isLoading } = useApi<{ results: Booking[] }>("/bookings/", ["bookings"]);
  return (
    <div className="max-w-5xl">
      <Seo title="Bookings" />
      <PageHeader eyebrow="Lessons" title="Bookings" actions={<CalendarButton />} />
      {isLoading && <Loading />}
      {data?.results.length === 0 && <EmptyState icon={CalendarDays} title="No bookings yet" action={<ButtonLink to="/parent/requests" icon={Search}>View your shortlists</ButtonLink>}>Book a tutor from a shortlist and your lessons will show up here.</EmptyState>}
      <div className="grid gap-4 md:grid-cols-2">
        {data?.results.map((b, i) => (
          <motion.div key={b.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
            <Link to={`/parent/bookings/${b.id}`} className="group block h-full rounded-3xl border border-ink-100 bg-white p-6 shadow-soft transition hover:border-brand-200 hover:shadow-lift">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <Avatar name={b.tutor_name} size={48} />
                  <div>
                    <p className="font-display text-lg font-bold text-ink-950">{b.tutor_name}</p>
                    <p className="text-sm text-ink-500">{b.subject_names.join(", ")} · {b.child_name}</p>
                  </div>
                </div>
                <StatusBadge status={b.status} label={b.status_display} />
              </div>
              <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-2xl bg-ink-50/80 p-3"><p className="text-xs text-ink-500">Next lesson</p><p className="font-semibold text-ink-900">{b.next_lesson ? dateTime(b.next_lesson) : "—"}</p></div>
                <div className="rounded-2xl bg-ink-50/80 p-3"><p className="text-xs text-ink-500">Progress</p><p className="font-semibold text-ink-900">{b.is_trial ? "Trial lesson" : `${b.lessons_done} of ${b.package_size} lessons`}</p></div>
              </div>
              {!b.is_trial && (
                <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-ink-100">
                  <div className="h-full rounded-full bg-gradient-to-r from-brand-500 to-brand-400" style={{ width: `${(b.lessons_done / b.package_size) * 100}%` }} />
                </div>
              )}
            </Link>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

export function ParentBookingDetail() {
  const { id } = useParams();
  const key = ["booking", id];
  const { data: b, isLoading } = useApi<Booking>(`/bookings/${id}/`, key);
  const [review, setReview] = useState(false);
  const [replace, setReplace] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const cancel = useAction(() => api.post(`/bookings/${id}/cancel/`, { reason: "Cancelled by parent" }), [key, ["wallet"]], { success: "Booking cancelled — payment returned to your wallet" });
  const renew = useAction((v: boolean) => api.patch(`/bookings/${id}/auto-renew/`, { auto_renew: v }), [key], { success: "Auto-renewal updated" });
  const payNow = useAction(() => api.post<{ payment: { authorization_url: string } | null }>(`/bookings/${id}/pay/`), [key, ["wallet"]]);
  const walletInfo = useApi<WalletData>("/wallet/", ["wallet"]);
  const card = walletInfo.data?.saved_cards[0];
  if (isLoading) return <Loading />;
  if (!b) return null;
  const month = todayISO().slice(0, 7);
  return (
    <div className="max-w-5xl">
      <Seo title={`Lessons with ${b.tutor_name}`} />
      <PageHeader back={{ to: "/parent/bookings", label: "Bookings" }} eyebrow={b.subject_names.join(" · ")}
        title={<span className="flex items-center gap-3"><Avatar name={b.tutor_name} size={44} />{b.child_name} with {b.tutor_name}</span>}
        actions={<>
          {b.thread_id && <ButtonLink variant="secondary" to={`/messages/${b.thread_id}`} icon={MessageSquare}>Message</ButtonLink>}
          {b.lessons_done > 0 && <Button variant="secondary" icon={Star} onClick={() => setReview(true)}>Rate tutor</Button>}
          <a className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-white px-4 text-sm font-semibold text-ink-800 shadow-soft ring-1 ring-ink-200 transition hover:bg-ink-50" href={`/api/bookings/${b.id}/progress-report/?month=${month}`}><Download className="size-4" />Progress report</a>
        </>} />
      <div className="mb-6 space-y-3">
        {b.status === "offered" && <Alert tone="amber" title="Waiting for the tutor">{b.tutor_name} has until {dateTime(b.offer_expires_at)} to accept. If they don't, we'll offer your booking to the next tutor on your shortlist.</Alert>}
        {b.status === "reassigning" && <Alert tone="amber" title="Finding you another tutor">Your payment stays safely held — our team will contact you shortly.</Alert>}
        {b.status === "awaiting_payment" && (
          <Alert tone="amber" title={b.renews ? "Your renewal is waiting for payment" : "This booking hasn't been paid yet"}>
            <p>{b.renews ? "We're holding the same tutor and time slots for you for 48 hours." : "It will be released if payment isn't completed within 2 hours."}</p>
            <Button className="mt-3" icon={WalletIcon} loading={payNow.isPending} onClick={() => payNow.mutate(undefined, {
              onSuccess: (r) => { if (r.payment) window.location.href = r.payment.authorization_url; },
            })}>Pay {naira(b.amount_due_kobo)}</Button>
            <ErrorAlert error={payNow.error} />
          </Alert>
        )}
        {b.renews && <Alert tone="blue">This package continues <Link className="font-semibold underline" to={`/parent/bookings/${b.renews}`}>your previous package</Link> with {b.tutor_name}.</Alert>}
        {b.renewed_by && <Alert tone="green">This package has been renewed. <Link className="font-semibold underline" to={`/parent/bookings/${b.renewed_by}`}>See the next package →</Link></Alert>}
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <Card title="Lessons" icon={CalendarDays} className="self-start">
          <ul className="space-y-3">
            {b.lessons?.map((l) => (
              <li key={l.id} className={cn("rounded-2xl border p-4 transition", l.codes ? "border-brand-200 bg-brand-50/40" : "border-ink-100")}>
                <div className="flex flex-wrap items-center gap-4">
                  <DateChip iso={l.scheduled_start} tone={l.codes ? "brand" : "light"} />
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-ink-900">{timeOnly(l.scheduled_start)} – {timeOnly(l.scheduled_end)}</p>
                    {l.checkin_at ? (
                      <p className="text-xs text-ink-500">Checked in {timeOnly(l.checkin_at)}{l.late_minutes > 10 ? ` · ${l.late_minutes} min late` : ""}{l.checkout_at ? ` · out ${timeOnly(l.checkout_at)}` : ""}</p>
                    ) : <p className="text-xs text-ink-500">{naira(l.amount_kobo)} held in escrow</p>}
                  </div>
                  <StatusBadge status={l.status} label={l.status_display} />
                </div>
                {l.codes && (
                  <div className="mt-4 flex flex-wrap gap-6 rounded-2xl bg-white p-4 ring-1 ring-brand-100">
                    {l.codes.checkin && <CodeDisplay label="Check-in code" code={l.codes.checkin} />}
                    <CodeDisplay label="Check-out code" code={l.codes.checkout} />
                  </div>
                )}
                {l.note_topics && (
                  <div className="mt-3 space-y-1 rounded-2xl bg-white p-4 text-sm ring-1 ring-ink-100">
                    <p className="text-xs font-semibold tracking-wider text-ink-400 uppercase">Lesson note</p>
                    <p><span className="font-semibold">Covered:</span> {l.note_topics}</p>
                    {l.note_homework && <p><span className="font-semibold">Homework:</span> {l.note_homework}</p>}
                    {l.note_observations && <p><span className="font-semibold">Notes:</span> {l.note_observations}</p>}
                  </div>
                )}
                <LessonActions lesson={l} invalidate={[key, ["wallet"]]} />
              </li>
            ))}
          </ul>
        </Card>
        <div className="space-y-4">
          <Card>
            <StatusBadge status={b.status} label={b.status_display} />
            <dl className="mt-4 space-y-3 text-sm">
              {[[Clock, "Schedule", fmtSchedule(b.schedule, b.lesson_minutes)], [Target, "Package", b.is_trial ? "Trial lesson" : `${b.lessons_done} of ${b.package_size} confirmed`],
                [Banknote, "Price", `${naira(b.lesson_price_kobo)} / lesson`], [MapPin, "Where", b.is_online ? "Online" : `${b.address_visible ?? ""}, ${b.area_name}`]].map(([I, k, v]) => {
                const Icon = I as typeof Clock;
                return <div key={k as string} className="flex gap-3"><Icon className="mt-0.5 size-4 shrink-0 text-brand-500" /><div><dt className="text-xs text-ink-500">{k as string}</dt><dd className="font-medium text-ink-900">{v as string}</dd></div></div>;
              })}
            </dl>
          </Card>
          <Card>
            <div className="space-y-3">
              {b.status === "active" && !b.is_trial && !b.renewed_by && (
                <div className="rounded-2xl bg-ink-50/70 p-3">
                  <Checkbox label="Renew this package automatically" checked={b.auto_renew} onChange={(e) => renew.mutate(e.target.checked)} />
                  <p className="mt-1.5 pl-8 text-xs leading-relaxed text-ink-500">
                    {b.auto_renew ? "Before the last lesson, we'll book the same slots again" : "Keep the same tutor and time slots"} — paid from your wallet first{card ? `, then your ${card.brand || "card"} ending ${card.last4}` : ""}. You can turn this off any time.
                  </p>
                </div>
              )}
              {b.status === "active" && <Button variant="secondary" className="w-full" icon={RefreshCw} onClick={() => setReplace(true)}>Request a different tutor</Button>}
              {["awaiting_payment", "offered", "reassigning"].includes(b.status) && <Button variant="danger" className="w-full" onClick={() => setConfirmCancel(true)}>Cancel booking</Button>}
              <p className="text-xs leading-relaxed text-ink-500">Replacements are free and your remaining balance moves with you.</p>
            </div>
          </Card>
        </div>
      </div>
      <Modal open={confirmCancel} onClose={() => setConfirmCancel(false)} title="Cancel this booking?" description="Any payment returns to your wallet."
        footer={<><Button variant="secondary" onClick={() => setConfirmCancel(false)}>Keep booking</Button><Button variant="danger" loading={cancel.isPending} onClick={() => cancel.mutate(undefined, { onSuccess: () => setConfirmCancel(false) })}>Cancel booking</Button></>}>
        <ErrorAlert error={cancel.error} />
      </Modal>
      {review && <ReviewModal booking={b} onClose={() => setReview(false)} />}
      {replace && <ReplaceModal bookingId={b.id} onClose={() => setReplace(false)} />}
    </div>
  );
}

function ReviewModal({ booking, onClose }: { booking: Booking; onClose: () => void }) {
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");
  const save = useAction(() => api.post("/reviews/", { booking: booking.id, rating, comment }), [], { success: "Thanks for your review!" });
  return (
    <Modal open onClose={onClose} title={`Rate ${booking.tutor_name}`} description="Your review helps other families choose with confidence."
      footer={<Button loading={save.isPending} onClick={() => save.mutate(undefined, { onSuccess: onClose })}>Submit review</Button>}>
      <ErrorAlert error={save.error} />
      <div className="flex justify-center py-2"><StarInput value={rating} onChange={setRating} /></div>
      <Textarea label="Comment (optional)" value={comment} onChange={(e) => setComment(e.target.value)} />
    </Modal>
  );
}

function ReplaceModal({ bookingId, onClose }: { bookingId: number; onClose: () => void }) {
  const [reason, setReason] = useState("");
  const send = useAction(() => api.post(`/bookings/${bookingId}/request-replacement/`, { reason }), [], { success: "Request sent — our team will be in touch shortly" });
  return (
    <Modal open onClose={onClose} title="Request a different tutor" description="Free of charge. Your remaining lessons carry over."
      footer={<Button loading={send.isPending} onClick={() => send.mutate(undefined, { onSuccess: onClose })}>Send request</Button>}>
      <ErrorAlert error={send.error} />
      <Textarea label="What isn't working? (helps us match better)" value={reason} onChange={(e) => setReason(e.target.value)} />
    </Modal>
  );
}

// --- Wallet ---------------------------------------------------------------

export function Wallet() {
  const wallet = useApi<WalletData>("/wallet/", ["wallet"]);
  const removeCard = useAction((cardId: number) => api.del(`/saved-cards/${cardId}/`), [["wallet"]], { success: "Card removed" });
  const payments = useApi<{ reference: string; amount_kobo: number; status: string; channel: string; created_at: string; booking: number | null }[]>("/payments/", ["payments"]);
  const [amount, setAmount] = useState("");
  const topup = useAction(() => api.post<{ authorization_url: string }>("/payments/topup/", { amount_kobo: toKobo(amount) }));
  return (
    <div className="max-w-5xl">
      <Seo title="Wallet & payments" />
      <PageHeader eyebrow="Money" title="Wallet & payments" />
      <div className="grid gap-5 lg:grid-cols-[1.2fr_1fr]">
        <div className="grain relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-ink-900 via-brand-950 to-brand-900 p-7 text-white shadow-lift">
          <div className="bg-grid pointer-events-none absolute inset-0 opacity-40" />
          <div className="absolute -right-16 -bottom-16 size-56 rounded-full bg-gold-400/20 blur-3xl" />
          <div className="relative">
            <p className="flex items-center gap-2 text-sm text-brand-100/80"><WalletIcon className="size-4 text-gold-300" /> Wallet balance</p>
            <p className="mt-2 font-display text-5xl font-bold tracking-tight">{naira(wallet.data?.balance_kobo)}</p>
            <div className="mt-8 flex items-end justify-between gap-4">
              <div>
                <p className="text-xs text-brand-100/60">Held in escrow for upcoming lessons</p>
                <p className="font-display text-xl font-semibold">{naira(wallet.data?.in_escrow_kobo)}</p>
              </div>
              <Badge className="bg-white/10 text-brand-100 ring-white/15">Protected by TutorBridge</Badge>
            </div>
          </div>
        </div>
        <Card title="Top up" icon={Plus} subtitle="Card, bank transfer or USSD">
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); topup.mutate(undefined, { onSuccess: (r) => { window.location.href = r.authorization_url; } }); }}>
            <div className="flex flex-wrap gap-2">
              {[10000, 25000, 50000, 100000].map((n) => (
                <button key={n} type="button" onClick={() => setAmount(String(n))} className={cn("rounded-full px-3.5 py-1.5 text-sm font-semibold ring-1 transition", amount === String(n) ? "bg-brand-600 text-white ring-brand-600" : "ring-ink-200 hover:ring-ink-300")}>{naira(n * 100)}</button>
              ))}
            </div>
            <Input label="Amount (₦)" icon={Banknote} inputMode="numeric" required value={amount} onChange={(e) => setAmount(e.target.value)} error={topup.error?.field("amount_kobo")} />
            <Button type="submit" className="w-full" loading={topup.isPending} iconRight={ArrowRight}>Continue to payment</Button>
          </form>
        </Card>
      </div>
      <Card className="mt-5" title="Saved cards" icon={CreditCard} subtitle="Used only for package auto-renewals you've switched on. We store a secure token from Paystack — never your card number.">
        {!wallet.data?.saved_cards.length ? (
          <p className="text-sm text-ink-500">No saved cards. A card is saved automatically when you pay by card, and you can remove it here at any time.</p>
        ) : (
          <ul className="divide-y divide-ink-100">
            {wallet.data.saved_cards.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-3 py-3">
                <span className="flex items-center gap-3">
                  <span className="flex h-9 w-14 items-center justify-center rounded-lg bg-gradient-to-br from-ink-800 to-ink-950 text-[10px] font-bold tracking-wider text-white uppercase">{c.brand || "Card"}</span>
                  <span><span className="font-semibold text-ink-900">•••• {c.last4}</span><span className="block text-xs text-ink-500">Expires {c.exp_month}/{c.exp_year.slice(-2)}</span></span>
                </span>
                <Button size="sm" variant="ghost" className="text-red-600" loading={removeCard.isPending} onClick={() => removeCard.mutate(c.id)}>Remove</Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <div>
          <h2 className="mb-3 font-display text-lg font-semibold">Payments</h2>
          {payments.data && (
            <Table head={["Date", "Amount", "Status", ""]} empty={!payments.data.length}>
              {payments.data.map((p) => (
                <tr key={p.reference} className="hover:bg-ink-50/50">
                  <Td><p className="font-medium text-ink-900">{dateOnly(p.created_at)}</p><p className="font-mono text-[11px] text-ink-400">{p.reference}</p></Td>
                  <Td className="font-semibold">{naira(p.amount_kobo)}</Td>
                  <Td><StatusBadge status={p.status} /></Td>
                  <Td>{p.status === "success" && <a className="inline-flex items-center gap-1 text-sm font-semibold text-brand-600 hover:underline" href={`/api/payments/${p.reference}/receipt/`}><Download className="size-3.5" />Receipt</a>}</Td>
                </tr>
              ))}
            </Table>
          )}
        </div>
        <div>
          <h2 className="mb-3 font-display text-lg font-semibold">Wallet activity</h2>
          {wallet.data && (
            <Table head={["Date", "Description", "Amount"]} empty={!wallet.data.entries.length}>
              {wallet.data.entries.map((e, i) => (
                <tr key={i} className="hover:bg-ink-50/50">
                  <Td className="whitespace-nowrap">{dateOnly(e.date)}</Td>
                  <Td>{e.description}</Td>
                  <Td className={cn("font-semibold whitespace-nowrap", e.amount_kobo >= 0 ? "text-brand-600" : "text-ink-700")}>{e.amount_kobo >= 0 ? "+" : "−"}{naira(Math.abs(e.amount_kobo))}</Td>
                </tr>
              ))}
            </Table>
          )}
        </div>
      </div>
    </div>
  );
}
