import { Activity, AlertTriangle, Banknote, CalendarDays, CheckCircle2, GraduationCap, Search, Send, Siren, TrendingUp, Users } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { greeting, WelcomeBanner } from "@/components/app";
import { Seo } from "@/components/Seo";
import { KeyValue } from "@/components/shared";
import { Alert, Badge, Button, Card, ErrorAlert, Input, Loading, Modal, PageHeader, Select, Stat, StatusBadge, Table, Td, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { hasPerm, useAuth } from "@/lib/auth";
import { dateOnly, dateTime, naira } from "@/lib/format";
import { useAction, useApi, useRefData } from "@/lib/hooks";

import { Json, usePaged } from "./common";

type Dash = Record<string, number | null>;

export function StaffDashboard() {
  const { me } = useAuth();
  const { data: d, isLoading } = useApi<Dash>("/staff/dashboard/", ["staff-dashboard"]);
  if (isLoading || !d) return <Loading />;
  const kpi = (label: string, v: number | null, target: number, lowerIsBetter = false) => {
    const ok = v !== null && (lowerIsBetter ? v <= target : v >= target);
    return (
      <div className="rounded-2xl bg-white/10 p-4 ring-1 ring-white/15">
        <p className="text-xs text-brand-100/70">{label}</p>
        <p className="mt-1 font-display text-3xl font-bold">{v === null ? "—" : `${v}%`}</p>
        <p className={cn("mt-1 flex items-center gap-1 text-xs font-semibold", v === null ? "text-white/50" : ok ? "text-brand-300" : "text-gold-300")}>
          {v === null ? "No data yet" : ok ? <><CheckCircle2 className="size-3.5" /> On target</> : <><AlertTriangle className="size-3.5" /> Target {lowerIsBetter ? "≤" : "≥"} {target}%</>}
        </p>
      </div>
    );
  };
  return (
    <div>
      <Seo title="Staff dashboard" />
      <WelcomeBanner greeting={greeting()} title={`${me?.first_name}, here's today`} subtitle="Operations at a glance — last 30 days unless stated."
        aside={<div className="grid grid-cols-2 gap-3">{kpi("Fill rate", d.fill_rate_30d, 80)}{kpi("Lesson completion", d.lesson_completion_30d, 95)}{kpi("Tutor no-shows", d.no_show_rate_30d, 2, true)}{kpi("Trial → package", d.trial_conversion_60d, 50)}</div>} />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Active parents" value={d.active_parents} icon={Users} />
        <Stat label="Active tutors" value={d.active_tutors} hint={`${d.tutors_in_vetting} in vetting`} icon={GraduationCap} iconTone="blue" />
        <Stat label="Open requests" value={d.open_requests} hint={`${d.requests_past_sla} past 24h SLA`} tone={d.requests_past_sla ? "red" : undefined} icon={Search} iconTone="gold" />
        <Stat label="Active bookings" value={d.active_bookings} hint={`${d.bookings_needing_tutor} need a tutor`} tone={d.bookings_needing_tutor ? "red" : undefined} icon={CalendarDays} iconTone="violet" />
        <Stat label="GMV" value={naira(d.gmv_30d_kobo)} icon={TrendingUp} />
        <Stat label="Platform revenue" value={naira(d.revenue_30d_kobo)} tone="green" icon={Banknote} />
        <Stat label="Payouts due" value={naira(d.payouts_due_kobo)} icon={Send} iconTone="blue" />
        <Stat label="Disputes / incidents" value={`${d.open_disputes} / ${d.open_incidents}`} tone={d.open_incidents ? "red" : undefined} icon={Siren} iconTone="red" />
      </div>
      {hasPerm(me, "audit.view") && <SystemHealth />}
    </div>
  );
}

type HealthCheck = { key: string; label: string; ok: boolean; detail: string };

/** Live operational checks (the same ones emailed to admins every morning). */
function SystemHealth() {
  const { data } = useApi<HealthCheck[]>("/staff/health/", ["staff-health"]);
  if (!data) return null;
  const problems = data.filter((c) => !c.ok).length;
  return (
    <Card className="mt-6" title="System health" icon={Activity}
      subtitle={problems ? `${problems} item${problems > 1 ? "s" : ""} need attention` : "All checks passing"}>
      <ul className="grid gap-2 sm:grid-cols-2">
        {[...data].sort((a, b) => Number(a.ok) - Number(b.ok)).map((c) => (
          <li key={c.key} className={cn("flex gap-3 rounded-2xl p-3 ring-1", c.ok ? "bg-white ring-ink-100" : "bg-red-50/60 ring-red-200")}>
            {c.ok ? <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-brand-500" /> : <AlertTriangle className="mt-0.5 size-5 shrink-0 text-red-500" />}
            <div className="min-w-0"><p className="text-sm font-semibold text-ink-900">{c.label}</p><p className="text-xs text-ink-500">{c.detail}</p></div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

type QueueRow = { id: number; user: { name: string; email: string; phone: string }; status: string; submitted_at: string | null; checks_passed: number; checks_total: number; needs_attention: number };

export function VettingQueue() {
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const { rows, isLoading, pager } = usePaged<QueueRow>("/staff/vetting/", { status, q });
  return (
    <div>
      <PageHeader title="Vetting queue" />
      <div className="mb-4 flex flex-wrap gap-3">
        <div className="w-48"><Select label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">In progress</option>{["applied", "under_review", "interview", "approved", "active", "rejected", "suspended"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
        </Select></div>
        <div className="w-64"><Input label="Search" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      </div>
      {isLoading ? <Loading /> : (
        <Table head={["Applicant", "Status", "Submitted", "Checks", "Needs review"]} empty={!rows.length}>
          {rows.map((r) => (
            <tr key={r.id}>
              <Td><Link className="font-medium text-brand-700 hover:underline" to={`/staff/vetting/${r.id}`}>{r.user.name}</Link><p className="text-xs text-slate-500">{r.user.email}</p></Td>
              <Td><StatusBadge status={r.status} /></Td>
              <Td>{dateOnly(r.submitted_at)}</Td>
              <Td>{r.checks_passed}/{r.checks_total}</Td>
              <Td>{r.needs_attention > 0 ? <Badge tone="amber">{r.needs_attention}</Badge> : "—"}</Td>
            </tr>
          ))}
        </Table>
      )}
      {pager}
    </div>
  );
}

type Check = { type: string; label: string; status: string; provider: string; result: unknown; notes: string; reviewer: string | null; reviewed_at: string | null };
type VDetail = {
  profile: { id: number; status: string; headline: string; bio: string; hourly_rate_kobo: number; highest_qualification: string; years_experience: number; trcn_number: string; subjects: { subject_name: string; level_name: string; test_score: number | null; verified: boolean }[]; areas: { name: string }[]; photo_url: string | null; background_valid_until: string | null };
  user: { id: number; name: string; email: string; phone: string; gender: string; email_verified: boolean; phone_verified: boolean };
  progress: { steps: { label: string; done: boolean }[] };
  checks: Check[];
  documents: { id: number; doc_type: string; label: string; name: string; status: string; review_note: string; created_at: string; url: string }[];
  references: { id: number; kind: string; name: string; email: string; phone: string; relationship: string; organisation: string; is_professional: boolean; submitted_at: string | null; response: Record<string, string> | null; call_verified: boolean; call_notes: string; id_document: string | null }[];
  tests: { subject: string; level: string; score_pct: number | null; passed: boolean; submitted_at: string | null }[];
  interviews: { id: number; starts_at: string; officer: string; meeting_link: string; outcome: string; notes: string }[];
  history: { from: string; to: string; by: string; reason: string; at: string }[];
  approval_blockers: string[];
  strikes: { reason: string; notes: string; at: string }[];
};

export function VettingDetail() {
  const { id } = useParams();
  const { me } = useAuth();
  const key = ["vetting", id];
  const { data: d, isLoading } = useApi<VDetail>(`/staff/vetting/${id}/`, key);
  const [checkDialog, setCheckDialog] = useState<Check | null>(null);
  const [decision, setDecision] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const decideCheck = useAction((status: string) => api.post(`/staff/vetting/${id}/check/`, { check_type: checkDialog!.type, status, notes }), [key]);
  const decide = useAction(() => api.post(`/staff/vetting/${id}/decision/`, { decision, reason: notes }), [key]);
  const reviewDoc = useAction((a: { id: number; status: string }) => api.post(`/staff/documents/${a.id}/review/`, { status: a.status, note: a.status === "rejected" ? prompt("Reason for rejecting this document?") ?? "" : "" }), [key]);
  const verifyRef = useAction((a: { id: number }) => api.post(`/staff/references/${a.id}/verify/`, { call_verified: true, call_notes: prompt("Call notes") ?? "" }), [key]);
  if (isLoading || !d) return <Loading />;
  const canReview = hasPerm(me, "vetting.review");
  const canDecide = hasPerm(me, "vetting.decide");
  const close = () => { setCheckDialog(null); setDecision(null); setNotes(""); };
  return (
    <div className="space-y-6">
      <PageHeader title={d.user.name} subtitle={<>{d.user.email} · {d.user.phone} · <StatusBadge status={d.profile.status} /></>} back={{ to: "/staff/vetting", label: "Vetting queue" }}
        actions={canDecide && <>
          <Button variant="secondary" onClick={() => setDecision("interview")}>Move to interview</Button>
          <Button onClick={() => setDecision("approve")} disabled={d.approval_blockers.length > 0}>Approve</Button>
          <Button variant="danger" onClick={() => setDecision("reject")}>Reject</Button>
        </>} />
      {d.approval_blockers.length > 0 && <Alert tone="amber">Before approval: {d.approval_blockers.join(", ")}</Alert>}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Profile" className="lg:col-span-2">
          <div className="flex gap-4">
            {d.profile.photo_url && <img src={d.profile.photo_url} alt="" className="h-24 w-24 rounded-lg object-cover" />}
            <div className="flex-1">
              <p className="font-semibold">{d.profile.headline}</p>
              <p className="mt-1 text-sm whitespace-pre-line text-slate-700">{d.profile.bio}</p>
            </div>
          </div>
          <div className="mt-4"><KeyValue items={[
            ["Rate", naira(d.profile.hourly_rate_kobo) + "/h"], ["Qualification", d.profile.highest_qualification], ["Experience", `${d.profile.years_experience} yrs`],
            ["TRCN", d.profile.trcn_number || "—"], ["Gender", d.user.gender || "—"], ["Areas", d.profile.areas.map((a) => a.name).join(", ")],
            ["Subjects", d.profile.subjects.map((s) => `${s.subject_name} (${s.level_name})${s.test_score !== null ? ` ${s.test_score}%` : ""}`).join("; ")],
            ["Background valid until", dateOnly(d.profile.background_valid_until)],
          ]} /></div>
        </Card>
        <Card title="Onboarding">
          <ul className="space-y-1 text-sm">{d.progress.steps.map((s) => <li key={s.label}>{s.done ? "✅" : "⬜"} {s.label}</li>)}</ul>
          <p className="mt-3 text-xs text-slate-500">Email {d.user.email_verified ? "verified" : "unverified"} · Phone {d.user.phone_verified ? "verified" : "unverified"}</p>
        </Card>
      </div>
      <Card title="Verification checklist">
        <Table head={["Check", "Status", "Provider / result", "Reviewer", ""]}>
          {d.checks.map((c) => (
            <tr key={c.type}>
              <Td className="font-medium">{c.label}</Td>
              <Td><StatusBadge status={c.status} />{c.notes && <p className="mt-1 text-xs text-slate-500">{c.notes}</p>}</Td>
              <Td>{c.provider && <p className="text-xs">{c.provider}</p>}{c.result ? <Json value={c.result} /> : null}</Td>
              <Td className="text-xs">{c.reviewer ? `${c.reviewer}, ${dateTime(c.reviewed_at)}` : "—"}</Td>
              <Td>{canReview && <Button variant="ghost" onClick={() => setCheckDialog(c)}>Decide</Button>}</Td>
            </tr>
          ))}
        </Table>
      </Card>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Documents">
          <ul className="divide-y divide-slate-100 text-sm">
            {d.documents.map((doc) => (
              <li key={doc.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span><a className="font-medium text-brand-700 hover:underline" href={doc.url} target="_blank" rel="noreferrer">{doc.label}</a> <span className="text-xs text-slate-500">{doc.name}</span> <StatusBadge status={doc.status} /></span>
                {canReview && doc.status === "pending" && <span className="flex gap-1">
                  <Button variant="ghost" onClick={() => reviewDoc.mutate({ id: doc.id, status: "accepted" })}>Accept</Button>
                  <Button variant="ghost" className="text-red-700" onClick={() => reviewDoc.mutate({ id: doc.id, status: "rejected" })}>Reject</Button>
                </span>}
              </li>
            ))}
          </ul>
        </Card>
        <Card title="References & guarantor">
          <ul className="space-y-3 text-sm">
            {d.references.map((r) => (
              <li key={r.id} className="rounded-lg bg-slate-50 p-3">
                <p className="font-medium">{r.name} — {r.kind}{r.is_professional ? " (professional)" : ""}</p>
                <p className="text-slate-600">{r.relationship}{r.organisation ? `, ${r.organisation}` : ""} · {r.email} · {r.phone}</p>
                {r.response ? <Json value={r.response} /> : <Badge tone="amber">No response yet</Badge>}
                {r.id_document && <a className="mt-1 block text-brand-700 underline" href={r.id_document} target="_blank" rel="noreferrer">Guarantor ID</a>}
                <p className="mt-1">{r.call_verified ? <Badge tone="green">Call verified</Badge> : canReview && <Button variant="ghost" onClick={() => verifyRef.mutate({ id: r.id })}>Mark call verified</Button>}{r.call_notes && <span className="ml-2 text-slate-500">{r.call_notes}</span>}</p>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Tests & interviews">
          <ul className="space-y-1 text-sm">{d.tests.map((t, i) => <li key={i}>{t.subject} / {t.level}: {t.score_pct ?? "—"}% {t.passed ? "✅" : ""} <span className="text-slate-500">{dateTime(t.submitted_at)}</span></li>)}</ul>
          <ul className="mt-3 space-y-1 text-sm">{d.interviews.map((iv) => <li key={iv.id}>Interview {dateTime(iv.starts_at)} with {iv.officer}: {iv.outcome || "scheduled"} {iv.notes && `— ${iv.notes}`}</li>)}</ul>
        </Card>
        <Card title="Decision history">
          <ul className="space-y-2 text-sm">{d.history.map((h, i) => <li key={i}><strong>{h.from} → {h.to}</strong> by {h.by} · {dateTime(h.at)}<br /><span className="text-slate-600">{h.reason}</span></li>)}</ul>
          {d.strikes.length > 0 && <><p className="mt-3 font-semibold">Strikes</p><ul className="text-sm">{d.strikes.map((s, i) => <li key={i}>{s.reason} · {dateTime(s.at)} {s.notes}</li>)}</ul></>}
        </Card>
      </div>
      <Modal open={!!checkDialog} onClose={close} title={`Decide: ${checkDialog?.label}`}
        footer={<>
          <Button variant="danger" loading={decideCheck.isPending} onClick={() => decideCheck.mutate("failed", { onSuccess: close })}>Fail</Button>
          <Button variant="secondary" loading={decideCheck.isPending} onClick={() => decideCheck.mutate("manual_review", { onSuccess: close })}>Needs review</Button>
          <Button loading={decideCheck.isPending} onClick={() => decideCheck.mutate("passed", { onSuccess: close })}>Pass</Button>
        </>}>
        <ErrorAlert error={decideCheck.error} />
        {checkDialog?.type === "background" && <Alert tone="blue">Passing the background check makes it valid for 12 months and activates an approved tutor.</Alert>}
        <Textarea label="Notes (required to fail)" value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Modal>
      <Modal open={!!decision} onClose={close} title={decision === "approve" ? "Approve tutor" : decision === "reject" ? "Reject application" : "Move to interview"}
        footer={<Button variant={decision === "reject" ? "danger" : "primary"} loading={decide.isPending} onClick={() => decide.mutate(undefined, { onSuccess: close })}>Confirm</Button>}>
        <ErrorAlert error={decide.error} />
        <Textarea label="Reason (logged with your name)" required value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Modal>
    </div>
  );
}

type SlotRow = { id: number; starts_at: string; duration_minutes: number; officer: string; meeting_link: string; tutor: { id: number; name: string } | null; outcome: string };

export function Interviews() {
  const { data, isLoading } = useApi<SlotRow[]>("/staff/interview-slots/", ["slots"]);
  const [f, setF] = useState({ starts_at: "", meeting_link: "", duration_minutes: 30 });
  const add = useAction(() => api.post("/staff/interview-slots/", f), [["slots"]]);
  const [outcome, setOutcome] = useState<SlotRow | null>(null);
  const [o, setO] = useState({ outcome: "pass", notes: "" });
  const record = useAction(() => api.post(`/staff/interview-slots/${outcome!.id}/outcome/`, o), [["slots"]]);
  return (
    <div className="space-y-6">
      <PageHeader title="Interviews" />
      <Card title="Publish a slot">
        <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); add.mutate(undefined, { onSuccess: () => setF({ ...f, starts_at: "" }) }); }}>
          <Input label="Starts at (Lagos time)" type="datetime-local" required value={f.starts_at} onChange={(e) => setF({ ...f, starts_at: e.target.value })} />
          <Input label="Meeting link" type="url" value={f.meeting_link} onChange={(e) => setF({ ...f, meeting_link: e.target.value })} />
          <Button type="submit" loading={add.isPending}>Add slot</Button>
        </form>
        <ErrorAlert error={add.error} />
      </Card>
      {isLoading ? <Loading /> : (
        <Table head={["When", "Officer", "Tutor", "Outcome", ""]} empty={!data?.length}>
          {data?.map((s) => (
            <tr key={s.id}>
              <Td>{dateTime(s.starts_at)}</Td><Td>{s.officer}</Td>
              <Td>{s.tutor ? <Link className="text-brand-700" to={`/staff/vetting/${s.tutor.id}`}>{s.tutor.name}</Link> : <span className="text-slate-400">Open</span>}</Td>
              <Td>{s.outcome ? <StatusBadge status={s.outcome === "pass" ? "passed" : "failed"} label={s.outcome} /> : "—"}</Td>
              <Td>{s.tutor && !s.outcome && <Button variant="ghost" onClick={() => setOutcome(s)}>Record outcome</Button>}</Td>
            </tr>
          ))}
        </Table>
      )}
      <Modal open={!!outcome} onClose={() => setOutcome(null)} title={`Interview outcome — ${outcome?.tutor?.name}`}
        footer={<Button loading={record.isPending} onClick={() => record.mutate(undefined, { onSuccess: () => setOutcome(null) })}>Save</Button>}>
        <ErrorAlert error={record.error} />
        <Select label="Outcome" value={o.outcome} onChange={(e) => setO({ ...o, outcome: e.target.value })}><option value="pass">Pass</option><option value="fail">Fail</option><option value="no_show">No-show</option></Select>
        <Textarea label="Notes: teaching demo, communication, safeguarding answers" value={o.notes} onChange={(e) => setO({ ...o, notes: e.target.value })} />
      </Modal>
    </div>
  );
}

type QRow = { id: number; subject: string; level: string; text: string; options: string[]; correct_index: number; is_active: boolean };

export function Questions() {
  const { data: ref } = useRefData();
  const [filter, setFilter] = useState({ subject: "", level: "" });
  const { rows, pager, isLoading } = usePaged<QRow>("/staff/questions/", filter);
  const [f, setF] = useState({ subject: "", level: "", text: "", options: ["", "", "", ""], correct_index: 0 });
  const add = useAction(() => api.post("/staff/questions/", { ...f, options: f.options.filter(Boolean) }), [["/staff/questions/"]]);
  const toggle = useAction((q: QRow) => api.patch(`/staff/questions/${q.id}/`, { is_active: !q.is_active }), [["/staff/questions/"]]);
  return (
    <div className="space-y-6">
      <PageHeader title="Subject test question bank" subtitle="Each subject/level needs at least 5 active questions; tests draw up to 20 at random." />
      <Card title="Add a question">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); add.mutate(undefined, { onSuccess: () => setF({ ...f, text: "", options: ["", "", "", ""], correct_index: 0 }) }); }}>
          <ErrorAlert error={add.error} />
          <div className="grid gap-3 sm:grid-cols-2">
            <Select label="Subject" required value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })}><option value="">—</option>{ref?.subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select>
            <Select label="Level" required value={f.level} onChange={(e) => setF({ ...f, level: e.target.value })}><option value="">—</option>{ref?.levels.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</Select>
          </div>
          <Textarea label="Question" required value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} />
          {f.options.map((o, i) => (
            <div key={i} className="flex items-end gap-2">
              <input type="radio" name="correct" aria-label={`Option ${i + 1} is correct`} checked={f.correct_index === i} onChange={() => setF({ ...f, correct_index: i })} className="mb-3 h-5 w-5" />
              <div className="flex-1"><Input label={`Option ${i + 1}${f.correct_index === i ? " (correct)" : ""}`} value={o} onChange={(e) => setF({ ...f, options: f.options.map((x, j) => (j === i ? e.target.value : x)) })} /></div>
            </div>
          ))}
          <Button type="submit" loading={add.isPending}>Add question</Button>
        </form>
      </Card>
      <div className="flex gap-3">
        <div className="w-48"><Select label="Subject" value={filter.subject} onChange={(e) => setFilter({ ...filter, subject: e.target.value })}><option value="">All</option>{ref?.subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select></div>
        <div className="w-48"><Select label="Level" value={filter.level} onChange={(e) => setFilter({ ...filter, level: e.target.value })}><option value="">All</option>{ref?.levels.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</Select></div>
      </div>
      {isLoading ? <Loading /> : (
        <Table head={["Subject", "Level", "Question", "Answer", "Active"]} empty={!rows.length}>
          {rows.map((q) => (
            <tr key={q.id}>
              <Td>{q.subject}</Td><Td>{q.level}</Td><Td>{q.text}</Td><Td>{q.options[q.correct_index]}</Td>
              <Td><Button variant="ghost" onClick={() => toggle.mutate(q)}>{q.is_active ? "Active" : "Inactive"}</Button></Td>
            </tr>
          ))}
        </Table>
      )}
      {pager}
    </div>
  );
}
