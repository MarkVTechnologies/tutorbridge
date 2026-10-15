import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { KeyValue } from "@/components/shared";
import { Alert, Badge, Button, Card, ErrorAlert, Input, Loading, Modal, PageHeader, Select, StatusBadge, Table, Td, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { hasPerm, useAuth } from "@/lib/auth";
import { dateOnly, dateTime, naira, relative, schedule as fmtSchedule } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Lesson, Slot, TutorPublic } from "@/lib/types";

import { usePaged } from "./common";

type ReqRow = { id: number; parent: string; child: string; subjects: string[]; area: string; status: string; sla_due_at: string; overdue: boolean; assigned_to: string | null; candidates: number };

export function StaffRequests() {
  const [status, setStatus] = useState("");
  const { rows, isLoading, pager } = usePaged<ReqRow>("/staff/requests/", { status });
  return (
    <div>
      <PageHeader title="Lesson requests" subtitle="Review the system's suggestions, adjust, and publish a shortlist within 24 hours." />
      <div className="mb-4 w-56"><Select label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="">Needs matching</option>{["shortlist_ready", "booked", "closed"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
      </Select></div>
      {isLoading ? <Loading /> : (
        <Table head={["Request", "Child", "Subjects", "Area", "SLA", "Candidates", "Owner"]} empty={!rows.length}>
          {rows.map((r) => (
            <tr key={r.id}>
              <Td><Link className="font-medium text-brand-700 hover:underline" to={`/staff/requests/${r.id}`}>#{r.id} · {r.parent}</Link><div><StatusBadge status={r.status} /></div></Td>
              <Td>{r.child}</Td><Td>{r.subjects.join(", ")}</Td><Td>{r.area}</Td>
              <Td>{r.overdue ? <Badge tone="red">Overdue</Badge> : relative(r.sla_due_at)}</Td>
              <Td>{r.candidates}</Td><Td>{r.assigned_to ?? "—"}</Td>
            </tr>
          ))}
        </Table>
      )}
      {pager}
    </div>
  );
}

type StaffMatch = { id: number; tutor: TutorPublic; tutor_full_name: string; score: string; breakdown: Record<string, unknown>; status: string; in_shortlist: boolean; rank: number; decline_reason: string };
type ReqDetail = {
  id: number; status: string; parent: { id: number; name: string; email: string; phone: string };
  child: { name: string; class_name: string; level: string; curriculum: string; special_needs: boolean; learning_notes: string };
  subjects: string[]; goals: string; schedule: Slot[]; lesson_minutes: number; start_date: string; area: string; address: string;
  budget_min_kobo: number; budget_max_kobo: number; preferences: Record<string, unknown>; is_online: boolean; sla_due_at: string; ops_notes: string;
  shortlist_published_at: string | null; matches: StaffMatch[];
};

export function StaffRequestDetail() {
  const { id } = useParams();
  const { me } = useAuth();
  const key = ["staff-request", id];
  const { data: r, isLoading } = useApi<ReqDetail>(`/staff/requests/${id}/`, key);
  const [notes, setNotes] = useState<string | null>(null);
  const [addTutor, setAddTutor] = useState("");
  const inv = [key];
  const update = useAction((body: Record<string, unknown>) => api.patch(`/staff/requests/${id}/`, body), inv);
  const rematch = useAction(() => api.post(`/staff/requests/${id}/rematch/`), inv);
  const add = useAction(() => api.post(`/staff/requests/${id}/add-tutor/`, { tutor: Number(addTutor) }), inv);
  const patchMatch = useAction((a: { id: number; body: Record<string, unknown> }) => api.patch(`/staff/matches/${a.id}/`, a.body), inv);
  const invite = useAction((mid: number) => api.post(`/staff/matches/${mid}/invite/`), inv);
  const publish = useAction(() => api.post(`/staff/requests/${id}/publish/`), inv);
  if (isLoading || !r) return <Loading />;
  const canMatch = hasPerm(me, "requests.match");
  const shortlisted = r.matches.filter((m) => m.in_shortlist).length;
  return (
    <div className="space-y-6">
      <PageHeader title={`Request #${r.id}`} subtitle={<>{r.parent.name} · <StatusBadge status={r.status} /> · SLA {dateTime(r.sla_due_at)}</>} back={{ to: "/staff/requests", label: "Requests" }}
        actions={canMatch && <>
          <Button variant="secondary" onClick={() => update.mutate({ assign_to_me: true })}>Assign to me</Button>
          <Button variant="secondary" loading={rematch.isPending} onClick={() => rematch.mutate()}>Re-run matching</Button>
          <Button loading={publish.isPending} disabled={!shortlisted} onClick={() => publish.mutate()}>Publish shortlist ({shortlisted})</Button>
        </>} />
      <ErrorAlert error={publish.error ?? update.error ?? rematch.error} />
      {r.shortlist_published_at && <Alert tone="green">Shortlist published {dateTime(r.shortlist_published_at)}.</Alert>}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="What the family needs" className="lg:col-span-2">
          <KeyValue items={[
            ["Child", `${r.child.name} · ${r.child.class_name} · ${r.child.level} · ${r.child.curriculum}`], ["Subjects", r.subjects.join(", ")],
            ["Schedule", fmtSchedule(r.schedule, r.lesson_minutes)], ["Start", dateOnly(r.start_date)], ["Where", r.is_online ? "Online" : `${r.area} — ${r.address}`],
            ["Budget", r.budget_max_kobo ? `≤ ${naira(r.budget_max_kobo)}/h` : "Flexible"], ["Preferences", JSON.stringify(r.preferences)], ["Special needs", r.child.special_needs ? "Yes" : "No"],
          ]} />
          {r.goals && <p className="mt-3 text-sm"><strong>Goals:</strong> {r.goals}</p>}
          {r.child.learning_notes && <p className="mt-1 text-sm"><strong>Learning notes:</strong> {r.child.learning_notes}</p>}
        </Card>
        <Card title="Ops notes">
          <Textarea label="Internal notes" value={notes ?? r.ops_notes} onChange={(e) => setNotes(e.target.value)} />
          <Button className="mt-2" variant="secondary" loading={update.isPending} onClick={() => update.mutate({ ops_notes: notes ?? r.ops_notes })}>Save notes</Button>
          <p className="mt-3 text-sm text-slate-600">Parent: {r.parent.email} · {r.parent.phone}</p>
        </Card>
      </div>
      <Card title="Candidates" actions={canMatch && (
        <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(undefined, { onSuccess: () => setAddTutor("") }); }}>
          <div className="w-36"><Input label="Add tutor by ID" inputMode="numeric" value={addTutor} onChange={(e) => setAddTutor(e.target.value)} /></div>
          <Button variant="secondary" loading={add.isPending}>Add</Button>
        </form>
      )}>
        <ErrorAlert error={add.error ?? patchMatch.error ?? invite.error} />
        {r.matches.length === 0 && <p className="text-slate-500">No tutors passed the hard filters (active, background valid, teaches every subject at this level and curriculum, serves the area, ≥80% availability overlap, preferences). Try adding a tutor manually or recruiting.</p>}
        <Table head={["Shortlist", "Tutor", "Score", "Breakdown", "Rate", "Status", ""]}>
          {r.matches.map((m) => (
            <tr key={m.id} className={m.in_shortlist ? "bg-brand-50" : ""}>
              <Td>
                <input type="checkbox" className="h-5 w-5" aria-label={`Shortlist ${m.tutor_full_name}`} disabled={!canMatch || m.status === "declined"} checked={m.in_shortlist}
                  onChange={(e) => patchMatch.mutate({ id: m.id, body: { in_shortlist: e.target.checked } })} />
                {m.in_shortlist && <input type="number" aria-label="Rank" className="ml-2 w-14 rounded border-slate-300 text-sm" defaultValue={m.rank}
                  onBlur={(e) => patchMatch.mutate({ id: m.id, body: { rank: Number(e.target.value) } })} />}
              </Td>
              <Td><Link to={`/tutors/${m.tutor.id}`} target="_blank" className="font-medium text-brand-700">{m.tutor_full_name}</Link><p className="text-xs text-slate-500">#{m.tutor.id} · {m.tutor.home_area_name} · {m.tutor.gender} · ★{Number(m.tutor.rating_avg).toFixed(1)} ({m.tutor.rating_count}) · rel {m.tutor.reliability_score}%</p></Td>
              <Td className="font-semibold">{Number(m.score).toFixed(1)}</Td>
              <Td className="text-xs">{Object.entries(m.breakdown).map(([k, v]) => <span key={k} className="mr-2 inline-block">{k}: {String(v)}</span>)}</Td>
              <Td>{naira(m.tutor.hourly_rate_kobo)}</Td>
              <Td><StatusBadge status={m.status} />{m.decline_reason && <p className="text-xs text-slate-500">{m.decline_reason}</p>}</Td>
              <Td>{canMatch && m.status === "suggested" && <Button variant="ghost" onClick={() => invite.mutate(m.id)}>Invite</Button>}
                {canMatch && <Button variant="ghost" className="text-slate-500" onClick={() => patchMatch.mutate({ id: m.id, body: { withdraw: true } })}>Remove</Button>}</Td>
            </tr>
          ))}
        </Table>
      </Card>
    </div>
  );
}

type BRow = { id: number; status: string; parent: string; tutor: string; child: string; package_size: number; total_kobo: number; created_at: string; offer_expires_at: string | null };

export function StaffBookings() {
  const [status, setStatus] = useState("");
  const { rows, isLoading, pager } = usePaged<BRow>("/staff/bookings/", { status });
  return (
    <div>
      <PageHeader title="Bookings" />
      <div className="mb-4 w-56"><Select label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="">All</option>{["awaiting_payment", "offered", "active", "reassigning", "completed", "cancelled", "replaced"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
      </Select></div>
      {isLoading ? <Loading /> : (
        <Table head={["Booking", "Parent", "Tutor", "Child", "Lessons", "Total", "Status"]} empty={!rows.length}>
          {rows.map((b) => (
            <tr key={b.id}>
              <Td><Link className="font-medium text-brand-700" to={`/staff/bookings/${b.id}`}>#{b.id}</Link><p className="text-xs text-slate-500">{dateOnly(b.created_at)}</p></Td>
              <Td>{b.parent}</Td><Td>{b.tutor}</Td><Td>{b.child}</Td><Td>{b.package_size}</Td><Td>{naira(b.total_kobo)}</Td>
              <Td><StatusBadge status={b.status} />{b.status === "offered" && <p className="text-xs text-slate-500">expires {relative(b.offer_expires_at)}</p>}</Td>
            </tr>
          ))}
        </Table>
      )}
      {pager}
    </div>
  );
}

type BDetail = {
  id: number; status: string; parent: { id: number; name: string; email: string; phone: string }; tutor: { id: number; name: string; email: string; phone: string; tutor_id: number };
  child: string; subjects: string[]; package_size: number; lesson_minutes: number; schedule: Slot[]; total_kobo: number; commission_pct: string; escrow_balance_kobo: number;
  address: string; request: number | null; declined_tutor_ids: number[]; replaces: number | null; lessons: (Lesson & { checkin_lat: string | null; checkin_lng: string | null })[];
};

export function StaffBookingDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { me } = useAuth();
  const key = ["staff-booking", id];
  const { data: b, isLoading } = useApi<BDetail>(`/staff/bookings/${id}/`, key);
  const [dialog, setDialog] = useState<null | "cancel" | "replace">(null);
  const [reason, setReason] = useState("");
  const [tutor, setTutor] = useState("");
  const act = useAction((op: string) => api.post<{ new_booking?: number }>(`/staff/bookings/${id}/${op}/`, { reason, tutor: Number(tutor) }), [key]);
  const noShow = useAction((lid: number) => api.post(`/staff/lessons/${lid}/no-show/`), [key]);
  if (isLoading || !b) return <Loading />;
  const canManage = hasPerm(me, "bookings.manage");
  return (
    <div className="space-y-6">
      <PageHeader title={`Booking #${b.id}`} subtitle={<StatusBadge status={b.status} />} back={{ to: "/staff/bookings", label: "Bookings" }}
        actions={canManage && <>
          {b.status === "reassigning" && <Button variant="secondary" loading={act.isPending} onClick={() => act.mutate("reassign")}>Offer to next shortlisted</Button>}
          {["active", "reassigning", "offered"].includes(b.status) && <Button variant="secondary" onClick={() => setDialog("replace")}>Replace tutor</Button>}
          {!["cancelled", "completed", "replaced"].includes(b.status) && <Button variant="danger" onClick={() => setDialog("cancel")}>Cancel booking</Button>}
        </>} />
      <ErrorAlert error={act.error ?? noShow.error} />
      <Card>
        <KeyValue items={[
          ["Parent", `${b.parent.name} · ${b.parent.phone}`], ["Tutor", `${b.tutor.name} (#${b.tutor.tutor_id}) · ${b.tutor.phone}`],
          ["Child", b.child], ["Subjects", b.subjects.join(", ")], ["Schedule", fmtSchedule(b.schedule, b.lesson_minutes)],
          ["Total", `${naira(b.total_kobo)} · commission ${b.commission_pct}%`], ["Escrow balance", naira(b.escrow_balance_kobo)], ["Address", b.address || "—"],
          ["Request", b.request ? <Link key="r" className="text-brand-700" to={`/staff/requests/${b.request}`}>#{b.request}</Link> : "—"],
          ["Declined by tutors", b.declined_tutor_ids.join(", ") || "—"],
        ]} />
      </Card>
      <Card title="Lessons">
        <Table head={["When", "Status", "Escrow", "Check-in", "Check-out", "Note", ""]}>
          {b.lessons.map((l) => (
            <tr key={l.id}>
              <Td>{dateTime(l.scheduled_start)}</Td><Td><StatusBadge status={l.status} /></Td><Td><StatusBadge status={l.escrow_status} /></Td>
              <Td className="text-xs">{dateTime(l.checkin_at)}{l.late_minutes > 0 && ` (+${l.late_minutes}m)`}{l.checkin_lat && <a className="block text-brand-700" target="_blank" rel="noreferrer" href={`https://www.openstreetmap.org/?mlat=${l.checkin_lat}&mlon=${l.checkin_lng}#map=17/${l.checkin_lat}/${l.checkin_lng}`}>location</a>}</Td>
              <Td className="text-xs">{dateTime(l.checkout_at)}</Td>
              <Td className="max-w-xs text-xs">{l.note_topics}</Td>
              <Td>{canManage && l.status === "scheduled" && new Date(l.scheduled_start) < new Date() && <Button variant="ghost" className="text-red-700" onClick={() => noShow.mutate(l.id)}>Mark no-show</Button>}</Td>
            </tr>
          ))}
        </Table>
      </Card>
      <Modal open={dialog === "cancel"} onClose={() => setDialog(null)} title="Cancel booking"
        footer={<Button variant="danger" loading={act.isPending} onClick={() => act.mutate("cancel", { onSuccess: () => setDialog(null) })}>Cancel and refund to wallet</Button>}>
        <p className="text-sm text-slate-600">All upcoming lessons are cancelled and their escrow returned to the parent's wallet.</p>
        <Textarea label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Modal>
      <Modal open={dialog === "replace"} onClose={() => setDialog(null)} title="Replace tutor"
        footer={<Button loading={act.isPending} onClick={() => act.mutate("replace", { onSuccess: (r) => { setDialog(null); if (r.new_booking) nav(`/staff/bookings/${r.new_booking}`); } })}>Transfer remaining balance</Button>}>
        <p className="text-sm text-slate-600">Remaining lessons' escrow moves to a new booking with the new tutor, at their rate. Any leftover returns to the parent's wallet.</p>
        <Input label="New tutor ID" inputMode="numeric" value={tutor} onChange={(e) => setTutor(e.target.value)} />
        <Textarea label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Modal>
    </div>
  );
}
