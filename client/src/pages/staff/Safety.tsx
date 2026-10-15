import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge, Button, Card, ErrorAlert, Input, Loading, Modal, PageHeader, Select, Stars, StatusBadge, Table, Td, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { hasPerm, useAuth } from "@/lib/auth";
import { dateTime, naira, toKobo } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import type { Lesson } from "@/lib/types";

import { usePaged } from "./common";

type U = { id: number; name: string; email: string; phone: string; role: string };
type DisputeRow = { id: number; status: string; reason: string; description: string; raised_by: U; lesson: Lesson; parent: string; tutor: string; assignee: string | null; resolution: string; refund_kobo: number; notes: string; created_at: string; evidence: string[] };

export function Disputes() {
  const { me } = useAuth();
  const [status, setStatus] = useState("");
  const { rows, isLoading, pager } = usePaged<DisputeRow>("/staff/disputes/", { status });
  const [resolving, setResolving] = useState<DisputeRow | null>(null);
  const [f, setF] = useState({ resolution: "reject", notes: "", refund: "" });
  const act = useAction((a: { id: number; body: Record<string, unknown> }) => api.post(`/staff/disputes/${a.id}/`, a.body), [["/staff/disputes/"]]);
  return (
    <div>
      <PageHeader title="Disputes" subtitle="A disputed lesson's payout is frozen until resolved." />
      <div className="mb-4 w-48"><Select label="Status" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">Open</option><option value="resolved">Resolved</option></Select></div>
      {isLoading ? <Loading /> : (
        <div className="space-y-4">
          {rows.length === 0 && <p className="text-slate-500">No disputes.</p>}
          {rows.map((d) => (
            <Card key={d.id} title={<>#{d.id} · {d.reason.replace("_", " ")} <StatusBadge status={d.status} /></>}
              actions={hasPerm(me, "disputes.resolve") && d.status !== "resolved" && <>
                {!d.assignee && <Button variant="secondary" onClick={() => act.mutate({ id: d.id, body: { assign_to_me: true } })}>Take it</Button>}
                <Button onClick={() => setResolving(d)}>Resolve</Button>
              </>}>
              <p className="text-sm text-slate-700">{d.description}</p>
              <p className="mt-2 text-sm text-slate-500">Raised by {d.raised_by.name} ({d.raised_by.role}) · {dateTime(d.created_at)} · Lesson {dateTime(d.lesson.scheduled_start)} · {d.parent} / {d.tutor} · {naira(d.lesson.amount_kobo)}</p>
              <p className="text-sm text-slate-500">Check-in {dateTime(d.lesson.checkin_at)} · out {dateTime(d.lesson.checkout_at)} · late {d.lesson.late_minutes} min · Note: {d.lesson.note_topics || "—"}</p>
              <p className="mt-1 text-sm"><Link className="text-brand-700" to={`/staff/bookings/${d.lesson.booking}`}>Open booking</Link>{d.assignee && ` · Assigned to ${d.assignee}`}</p>
              {d.status === "resolved" && <p className="mt-2 text-sm"><Badge tone="green">{d.resolution}</Badge> {d.refund_kobo > 0 && `refund ${naira(d.refund_kobo)}`} — {d.notes}</p>}
            </Card>
          ))}
        </div>
      )}
      {pager}
      <Modal open={!!resolving} onClose={() => setResolving(null)} title={`Resolve dispute #${resolving?.id}`}
        footer={<Button loading={act.isPending} onClick={() => act.mutate({ id: resolving!.id, body: { resolution: f.resolution, notes: f.notes, refund_kobo: f.resolution === "partial" ? toKobo(f.refund) : 0 } }, { onSuccess: () => setResolving(null) })}>Resolve</Button>}>
        <ErrorAlert error={act.error} />
        <Select label="Outcome" value={f.resolution} onChange={(e) => setF({ ...f, resolution: e.target.value })}>
          <option value="reject">Reject — release payment to tutor</option><option value="refund">Uphold — full refund to parent's wallet</option><option value="partial">Partial refund</option>
        </Select>
        {f.resolution === "partial" && <Input label={`Refund amount (₦, lesson is ${naira(resolving?.lesson.amount_kobo)})`} inputMode="numeric" value={f.refund} onChange={(e) => setF({ ...f, refund: e.target.value })} />}
        <Textarea label="Notes (shared with both parties)" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />
      </Modal>
    </div>
  );
}

type IncidentRow = { id: number; severity: string; status: string; reporter: U; subject_user: U | null; lesson: number | null; booking: number | null; description: string; assignee: string | null; actions_taken: string; acknowledged_at: string | null; resolved_at: string | null; created_at: string };

export function Incidents() {
  const { me } = useAuth();
  const [status, setStatus] = useState("");
  const { rows, isLoading, pager } = usePaged<IncidentRow>("/staff/incidents/", { status });
  const [editing, setEditing] = useState<IncidentRow | null>(null);
  const [actions, setActions] = useState("");
  const [suspend, setSuspend] = useState<U | null>(null);
  const [reason, setReason] = useState("");
  const update = useAction((a: { id: number; body: Record<string, unknown> }) => api.patch(`/staff/incidents/${a.id}/`, a.body), [["/staff/incidents/"]]);
  const doSuspend = useAction((op: string) => api.post(`/staff/users/${suspend!.id}/suspend/`, { op, reason }), [["/staff/incidents/"]]);
  const canAct = hasPerm(me, "safety.act");
  return (
    <div>
      <PageHeader title="Safety incidents" subtitle="Every report is investigated within 24 hours. Zero tolerance." />
      <div className="mb-4 w-48"><Select label="Status" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option><option value="open">Open</option><option value="investigating">Investigating</option><option value="resolved">Resolved</option></Select></div>
      {isLoading ? <Loading /> : (
        <div className="space-y-4">
          {rows.length === 0 && <p className="text-slate-500">No incidents.</p>}
          {rows.map((i) => (
            <Card key={i.id} className={i.status === "open" ? "border-red-300" : ""} title={<>#{i.id} <StatusBadge status={i.severity} /> <StatusBadge status={i.status} /></>}
              actions={canAct && i.status !== "resolved" && <>
                {!i.acknowledged_at && <Button onClick={() => update.mutate({ id: i.id, body: { acknowledge: true } })}>Acknowledge</Button>}
                <Button variant="secondary" onClick={() => { setEditing(i); setActions(i.actions_taken); }}>Record actions</Button>
                {i.subject_user && hasPerm(me, "users.suspend") && <Button variant="danger" onClick={() => setSuspend(i.subject_user)}>Suspend {i.subject_user.name.split(" ")[0]}</Button>}
              </>}>
              <p className="whitespace-pre-line text-slate-800">{i.description}</p>
              <p className="mt-2 text-sm text-slate-500">Reported by {i.reporter.name} ({i.reporter.role}, {i.reporter.phone}) · {dateTime(i.created_at)}{i.subject_user && ` · About ${i.subject_user.name} (${i.subject_user.role}, ${i.subject_user.phone})`}</p>
              {i.booking && <Link className="text-sm text-brand-700" to={`/staff/bookings/${i.booking}`}>Booking #{i.booking}</Link>}
              {i.actions_taken && <p className="mt-2 rounded bg-slate-50 p-2 text-sm"><strong>Actions:</strong> {i.actions_taken}</p>}
            </Card>
          ))}
        </div>
      )}
      {pager}
      <Modal open={!!editing} onClose={() => setEditing(null)} title={`Incident #${editing?.id}`}
        footer={<>
          <Button variant="secondary" loading={update.isPending} onClick={() => update.mutate({ id: editing!.id, body: { actions_taken: actions } }, { onSuccess: () => setEditing(null) })}>Save</Button>
          <Button loading={update.isPending} onClick={() => update.mutate({ id: editing!.id, body: { actions_taken: actions, resolve: true } }, { onSuccess: () => setEditing(null) })}>Save & resolve</Button>
        </>}>
        <ErrorAlert error={update.error} />
        <Textarea label="Actions taken" value={actions} onChange={(e) => setActions(e.target.value)} />
      </Modal>
      <Modal open={!!suspend} onClose={() => setSuspend(null)} title={`Suspend ${suspend?.name}`}
        footer={<>
          <Button variant="danger" loading={doSuspend.isPending} onClick={() => doSuspend.mutate("ban", { onSuccess: () => setSuspend(null) })}>Ban permanently</Button>
          <Button variant="danger" loading={doSuspend.isPending} onClick={() => doSuspend.mutate("suspend", { onSuccess: () => setSuspend(null) })}>Suspend</Button>
        </>}>
        <p className="text-sm text-slate-600">Suspended tutors are hidden immediately, signed out, and their bookings are reassigned.</p>
        <ErrorAlert error={doSuspend.error} />
        <Textarea label="Reason (logged)" required value={reason} onChange={(e) => setReason(e.target.value)} />
      </Modal>
    </div>
  );
}

type Flagged = { id: number; thread: number; sender: U; body: string; original_body: string; created_at: string };

export function FlaggedMessages() {
  const { rows, isLoading, pager } = usePaged<Flagged>("/staff/flagged-messages/");
  return (
    <div>
      <PageHeader title="Flagged messages" subtitle="Messages where contact details were masked. Viewing is audit-logged." />
      {isLoading ? <Loading /> : (
        <Table head={["When", "Sender", "Shown as", "Original"]} empty={!rows.length}>
          {rows.map((m) => (
            <tr key={m.id}><Td>{dateTime(m.created_at)}</Td><Td>{m.sender.name}<p className="text-xs text-slate-500">{m.sender.role}</p></Td><Td>{m.body}</Td><Td className="text-red-700">{m.original_body}</Td></tr>
          ))}
        </Table>
      )}
      {pager}
    </div>
  );
}

type ReviewRow = { id: number; direction: string; author: string; rating: number; comment: string; tutor: string; is_hidden: boolean; hidden_reason: string; created_at: string };

export function Reviews() {
  const { rows, isLoading, pager } = usePaged<ReviewRow>("/staff/reviews/");
  const [hiding, setHiding] = useState<ReviewRow | null>(null);
  const [reason, setReason] = useState("");
  const vis = useAction((a: { id: number; hide: boolean }) => api.post(`/staff/reviews/${a.id}/visibility/`, { hide: a.hide, reason }), [["/staff/reviews/"]]);
  return (
    <div>
      <PageHeader title="Reviews" subtitle="Hide abusive reviews with a reason. Tutor→parent ratings are private." />
      {isLoading ? <Loading /> : (
        <Table head={["When", "Type", "Author", "Tutor", "Rating", "Comment", ""]} empty={!rows.length}>
          {rows.map((r) => (
            <tr key={r.id} className={r.is_hidden ? "opacity-60" : ""}>
              <Td>{dateTime(r.created_at)}</Td><Td className="text-xs">{r.direction.replace(/_/g, " ")}</Td><Td>{r.author}</Td><Td>{r.tutor}</Td><Td><Stars value={r.rating} /></Td><Td>{r.comment}{r.is_hidden && <p className="text-xs text-red-600">Hidden: {r.hidden_reason}</p>}</Td>
              <Td>{r.is_hidden ? <Button variant="ghost" onClick={() => vis.mutate({ id: r.id, hide: false })}>Unhide</Button> : <Button variant="ghost" onClick={() => setHiding(r)}>Hide</Button>}</Td>
            </tr>
          ))}
        </Table>
      )}
      {pager}
      <Modal open={!!hiding} onClose={() => setHiding(null)} title="Hide review" footer={<Button loading={vis.isPending} onClick={() => vis.mutate({ id: hiding!.id, hide: true }, { onSuccess: () => setHiding(null) })}>Hide</Button>}>
        <ErrorAlert error={vis.error} />
        <Textarea label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Modal>
    </div>
  );
}
