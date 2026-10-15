import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { KeyValue } from "@/components/shared";
import { Alert, Badge, Button, Card, ErrorAlert, Input, Loading, Modal, PageHeader, Select, StatusBadge, Table, Td, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { hasPerm, useAuth } from "@/lib/auth";
import { dateTime, naira, toKobo } from "@/lib/format";
import { useAction, useApi, useRefData } from "@/lib/hooks";

import { Json, usePaged } from "./common";

type URow = { id: number; name: string; email: string; phone: string; role: string; suspended: boolean; date_joined: string; last_login: string | null; verified: boolean };

export function Users() {
  const [f, setF] = useState({ q: "", role: "", suspended: "" });
  const { rows, isLoading, pager } = usePaged<URow>("/staff/users/", f);
  return (
    <div>
      <PageHeader title="Users" />
      <div className="mb-4 flex flex-wrap gap-3">
        <div className="w-64"><Input label="Search name, email, phone" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} /></div>
        <div className="w-44"><Select label="Role" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}><option value="">All</option><option value="parent">Parent</option><option value="tutor">Tutor</option></Select></div>
        <div className="w-44"><Select label="Suspended" value={f.suspended} onChange={(e) => setF({ ...f, suspended: e.target.value })}><option value="">Any</option><option value="1">Suspended only</option></Select></div>
      </div>
      {isLoading ? <Loading /> : (
        <Table head={["Name", "Contact", "Role", "Joined", "Last login", "State"]} empty={!rows.length}>
          {rows.map((u) => (
            <tr key={u.id}>
              <Td><Link className="font-medium text-brand-700" to={`/staff/users/${u.id}`}>{u.name}</Link></Td>
              <Td className="text-xs">{u.email}<br />{u.phone}</Td><Td>{u.role.replace("_", " ")}</Td><Td>{dateTime(u.date_joined)}</Td><Td>{dateTime(u.last_login)}</Td>
              <Td>{u.suspended ? <Badge tone="red">Suspended</Badge> : u.verified ? <Badge tone="green">Verified</Badge> : <Badge>Unverified</Badge>}</Td>
            </tr>
          ))}
        </Table>
      )}
      {pager}
    </div>
  );
}

type UDetail = URow & {
  gender: string; email_verified_at: string | null; phone_verified_at: string | null; suspension_reason: string; totp_enabled: boolean;
  parent?: { id: number; area: string | null; wallet_kobo: number; bookings: number; cancellations: number };
  tutor?: { id: number; status: string; tier: string; rating_avg: string; reliability_score: number; earnings_kobo: number; strikes: number };
  activity: { action: string; entity_type: string; entity_id: string; reason: string; created_at: string; ip: string | null }[];
};

export function UserDetail() {
  const { id } = useParams();
  const { me } = useAuth();
  const key = ["staff-user", id];
  const { data: u, isLoading } = useApi<UDetail>(`/staff/users/${id}/`, key);
  const [dialog, setDialog] = useState<null | "suspend" | "refund" | "strike">(null);
  const [reason, setReason] = useState("");
  const [amount, setAmount] = useState("");
  const [totp, setTotp] = useState("");
  const suspend = useAction((op: string) => api.post(`/staff/users/${id}/suspend/`, { op, reason }), [key]);
  const refund = useAction(() => api.post(`/staff/parents/${u!.parent!.id}/wallet-refund/`, { amount_kobo: toKobo(amount), totp }), [key]);
  const strike = useAction(() => api.post(`/staff/tutors/${u!.tutor!.id}/strikes/`, { reason: "policy_breach", notes: reason }), [key]);
  if (isLoading || !u) return <Loading />;
  const close = () => { setDialog(null); setReason(""); };
  return (
    <div className="space-y-6">
      <PageHeader title={u.name} subtitle={`${u.role.replace("_", " ")} · ${u.email} · ${u.phone}`} back={{ to: "/staff/users", label: "Users" }}
        actions={<>
          {hasPerm(me, "users.suspend") && (u.suspended ? <Button variant="secondary" onClick={() => setDialog("suspend")}>Reinstate</Button> : <Button variant="danger" onClick={() => setDialog("suspend")}>Suspend / ban</Button>)}
          {u.parent && hasPerm(me, "refunds.process") && <Button variant="secondary" onClick={() => setDialog("refund")}>Wallet cash refund</Button>}
          {u.tutor && hasPerm(me, "safety.act") && <Button variant="secondary" onClick={() => setDialog("strike")}>Add strike</Button>}
          {u.tutor && <Link to={`/staff/vetting/${u.tutor.id}`} className="self-center text-sm font-semibold text-brand-700">Vetting file →</Link>}
        </>} />
      {u.suspended && <Alert>Suspended: {u.suspension_reason}</Alert>}
      <Card>
        <KeyValue items={[
          ["Email verified", dateTime(u.email_verified_at)], ["Phone verified", dateTime(u.phone_verified_at)], ["2FA", u.totp_enabled ? "On" : "Off"], ["Last login", dateTime(u.last_login)],
          ...(u.parent ? [["Wallet", naira(u.parent.wallet_kobo)], ["Bookings", String(u.parent.bookings)], ["Cancellations", String(u.parent.cancellations)], ["Area", u.parent.area ?? "—"]] as [string, string][] : []),
          ...(u.tutor ? [["Tutor status", u.tutor.status], ["Tier", u.tutor.tier], ["Rating", u.tutor.rating_avg], ["Reliability", `${u.tutor.reliability_score}%`], ["Earnings balance", naira(u.tutor.earnings_kobo)], ["Strikes", String(u.tutor.strikes)]] as [string, string][] : []),
        ]} />
      </Card>
      <Card title="Activity history">
        <Table head={["When", "Action", "Entity", "Reason", "IP"]} empty={!u.activity.length}>
          {u.activity.map((a, i) => <tr key={i}><Td>{dateTime(a.created_at)}</Td><Td>{a.action}</Td><Td>{a.entity_type} #{a.entity_id}</Td><Td>{a.reason}</Td><Td className="text-xs">{a.ip}</Td></tr>)}
        </Table>
      </Card>
      <Modal open={dialog === "suspend"} onClose={close} title={u.suspended ? "Reinstate user" : "Suspend user"}
        footer={u.suspended ? <Button loading={suspend.isPending} onClick={() => suspend.mutate("reinstate", { onSuccess: close })}>Reinstate</Button> : <>
          <Button variant="danger" loading={suspend.isPending} onClick={() => suspend.mutate("ban", { onSuccess: close })}>Ban</Button>
          <Button variant="danger" loading={suspend.isPending} onClick={() => suspend.mutate("suspend", { onSuccess: close })}>Suspend</Button>
        </>}>
        <ErrorAlert error={suspend.error} />
        <Textarea label="Reason (logged)" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Modal>
      <Modal open={dialog === "refund"} onClose={close} title="Cash refund from wallet"
        footer={<Button loading={refund.isPending} onClick={() => refund.mutate(undefined, { onSuccess: close })}>Record refund</Button>}>
        <p className="text-sm text-slate-600">Records the refund in the ledger. Send the money via the gateway dashboard or bank transfer, minus gateway costs.</p>
        <ErrorAlert error={refund.error} />
        <Input label="Amount (₦)" inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <Input label="Authenticator code" inputMode="numeric" maxLength={6} value={totp} onChange={(e) => setTotp(e.target.value)} />
      </Modal>
      <Modal open={dialog === "strike"} onClose={close} title="Add strike" footer={<Button variant="danger" loading={strike.isPending} onClick={() => strike.mutate(undefined, { onSuccess: close })}>Add strike</Button>}>
        <ErrorAlert error={strike.error} />
        <Textarea label="Policy breach details" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Modal>
    </div>
  );
}

const SETTING_LABELS: Record<string, string> = {
  commission_pct_standard: "Default commission (%)",
  commission_pct_by_tier: "Commission by tutor tier (%)",
  matching_fee_kobo: "Matching fee (₦)",
  vetting_fee_kobo: "Tutor vetting fee (₦)",
  vetting_fee_deduct_from_earnings: "Deduct vetting fee from first earnings",
  pass_gateway_fee_to_parent: "Pass gateway fees to parents",
  booking_accept_hours: "Hours a tutor has to accept a booking",
  dispute_window_hours: "Dispute window after a lesson (hours)",
  late_cancel_notice_hours: "Late cancellation threshold (hours)",
  late_cancel_tutor_pct: "Late cancellation share paid to tutor (%)",
  payout_min_kobo: "Minimum payout (₦)",
  match_weights: "Matching weights",
  active_gateway: "Active payment gateway",
};

/** Money settings are stored in kobo but edited in naira; booleans as switches; nested values as JSON. */
function toDraft(k: string, v: unknown) {
  return k.endsWith("_kobo") ? String((v as number) / 100) : typeof v === "object" ? JSON.stringify(v) : String(v);
}
function fromDraft(k: string, v: string, original: unknown) {
  if (k.endsWith("_kobo")) return toKobo(v);
  if (typeof original === "boolean") return v === "true";
  if (typeof original === "number") return Number(v);
  if (typeof original === "object") return JSON.parse(v);
  return v;
}

export function Settings() {
  const { me } = useAuth();
  const { data, isLoading } = useApi<Record<string, unknown>>("/staff/settings/", ["settings"]);
  const { data: ref } = useRefData();
  const [draft, setDraft] = useState<Record<string, string>>({});
  useEffect(() => { if (data) setDraft(Object.fromEntries(Object.entries(data).map(([k, v]) => [k, toDraft(k, v)]))); }, [data]);
  const canEdit = hasPerm(me, "settings.manage");
  const [parseErr, setParseErr] = useState<string | null>(null);
  const save = useAction((body: Record<string, unknown>) => api.put("/staff/settings/", body), [["settings"], ["ref"]], { success: "Settings saved" });
  const band = useAction((a: { id: number; min: string; max: string }) => api.patch(`/staff/levels/${a.id}/`, { min_rate_kobo: toKobo(a.min), max_rate_kobo: toKobo(a.max) }), [["ref"]], { success: "Rate band saved" });
  const addSubject = useAction((name: string) => api.post("/staff/subjects/", { name }), [["ref"]], { success: "Subject added" });
  const [subject, setSubject] = useState("");
  if (isLoading || !data) return <Loading />;
  const changed = Object.entries(draft).filter(([k, v]) => v !== toDraft(k, data[k]));
  const submit = () => {
    try {
      setParseErr(null);
      save.mutate(Object.fromEntries(changed.map(([k, v]) => [k, fromDraft(k, v, data[k])])));
    } catch {
      setParseErr("One of the advanced values isn't valid JSON.");
    }
  };
  return (
    <div className="space-y-6">
      <PageHeader title="Configuration" subtitle="Fees, policies and matching. Every change is audit-logged." actions={canEdit && <Button disabled={!changed.length} loading={save.isPending} onClick={submit}>Save {changed.length || ""} change(s)</Button>} />
      {parseErr && <Alert>{parseErr}</Alert>}
      <ErrorAlert error={save.error} />
      <Card title="Business rules">
        <div className="grid gap-4 md:grid-cols-2">
          {Object.keys(data).map((k) => {
            const label = SETTING_LABELS[k] ?? k.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
            if (typeof data[k] === "boolean") {
              return <Select key={k} label={label} disabled={!canEdit} value={draft[k] ?? ""} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}><option value="true">Yes</option><option value="false">No</option></Select>;
            }
            if (k === "active_gateway") {
              return <Select key={k} label={label} disabled={!canEdit} value={draft[k] ?? ""} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}><option value="paystack">Paystack</option><option value="flutterwave">Flutterwave</option></Select>;
            }
            const advanced = typeof data[k] === "object";
            return <Input key={k} label={label} hint={advanced ? "Advanced: JSON" : undefined} inputMode={advanced ? undefined : "decimal"} disabled={!canEdit} value={draft[k] ?? ""} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />;
          })}
        </div>
      </Card>
      <Card title="Rate bands per level (₦/hour)">
        <ErrorAlert error={band.error} />
        <Table head={["Level", "Minimum", "Maximum", ""]}>
          {ref?.levels.map((l) => <BandRow key={l.id} level={l} disabled={!canEdit} onSave={(min, max) => band.mutate({ id: l.id, min, max })} />)}
        </Table>
      </Card>
      {canEdit && (
        <Card title="Subjects">
          <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); addSubject.mutate(subject, { onSuccess: () => setSubject("") }); }}>
            <div className="w-64"><Input label="New subject" value={subject} onChange={(e) => setSubject(e.target.value)} /></div>
            <Button loading={addSubject.isPending}>Add</Button>
          </form>
          <p className="mt-3 text-sm text-ink-600">{ref?.subjects.map((s) => s.name).join(" · ")}</p>
        </Card>
      )}
    </div>
  );
}

function BandRow({ level, disabled, onSave }: { level: { id: number; name: string; min_rate_kobo: number; max_rate_kobo: number }; disabled: boolean; onSave: (min: string, max: string) => void }) {
  const [min, setMin] = useState(String(level.min_rate_kobo / 100));
  const [max, setMax] = useState(String(level.max_rate_kobo / 100));
  return (
    <tr>
      <Td>{level.name}</Td>
      <Td><input aria-label={`${level.name} minimum`} className="input w-28" disabled={disabled} value={min} onChange={(e) => setMin(e.target.value)} /></Td>
      <Td><input aria-label={`${level.name} maximum`} className="input w-28" disabled={disabled} value={max} onChange={(e) => setMax(e.target.value)} /></Td>
      <Td>{!disabled && <Button variant="ghost" onClick={() => onSave(min, max)}>Save</Button>}</Td>
    </tr>
  );
}

const ROLES = [["vetting_officer", "Vetting officer"], ["ops_officer", "Operations / matching"], ["finance_officer", "Finance officer"], ["safety_officer", "Safety officer"], ["super_admin", "Super admin"]];

type StaffRow = URow & { extra_permissions: string[]; totp_enabled: boolean };

export function StaffAccounts() {
  const { data, isLoading } = useApi<StaffRow[]>("/staff/staff-accounts/", ["staff-accounts"]);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ first_name: "", last_name: "", email: "", phone: "", role: "ops_officer", password: "" });
  const create = useAction(() => api.post("/staff/staff-accounts/", f), [["staff-accounts"]]);
  const update = useAction((a: { id: number; body: Record<string, unknown> }) => api.patch(`/staff/staff-accounts/${a.id}/`, a.body), [["staff-accounts"]]);
  return (
    <div>
      <PageHeader title="Staff accounts" subtitle="Two-factor authentication is mandatory for all staff." actions={<Button onClick={() => setOpen(true)}>Add staff member</Button>} />
      <ErrorAlert error={update.error} />
      {isLoading ? <Loading /> : (
        <Table head={["Name", "Email", "Role", "2FA", "Last login", ""]} empty={!data?.length}>
          {data?.map((s) => (
            <tr key={s.id}>
              <Td>{s.name}</Td><Td>{s.email}</Td>
              <Td><select className="input" aria-label="Role" value={s.role} onChange={(e) => update.mutate({ id: s.id, body: { role: e.target.value } })}>{ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Td>
              <Td>{s.totp_enabled ? <Badge tone="green">On</Badge> : <Badge tone="amber">Pending setup</Badge>}</Td>
              <Td>{dateTime(s.last_login)}</Td>
              <Td><StatusBadge status={s.suspended ? "suspended" : "active"} /></Td>
            </tr>
          ))}
        </Table>
      )}
      <Modal open={open} onClose={() => setOpen(false)} title="Add staff member" footer={<Button loading={create.isPending} onClick={() => create.mutate(undefined, { onSuccess: () => setOpen(false) })}>Create</Button>}>
        <ErrorAlert error={create.error} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="First name" value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} />
          <Input label="Last name" value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} />
        </div>
        <Input label="Email" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        <Input label="Phone" type="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />
        <Select label="Role" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>
        <Input label="Temporary password" type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} hint="They'll set up 2FA at first sign-in." />
      </Modal>
    </div>
  );
}

type AuditRow = { id: number; actor: string; action: string; entity_type: string; entity_id: string; before: unknown; after: unknown; reason: string; ip: string | null; created_at: string };

export function AuditLog() {
  const [f, setF] = useState({ action: "", entity_type: "", entity_id: "" });
  const { rows, isLoading, pager } = usePaged<AuditRow>("/staff/audit/", f);
  return (
    <div>
      <PageHeader title="Audit log" subtitle="Immutable record of staff actions and money movements." />
      <div className="mb-4 flex flex-wrap gap-3">
        <div className="w-48"><Input label="Action starts with" value={f.action} onChange={(e) => setF({ ...f, action: e.target.value })} /></div>
        <div className="w-40"><Input label="Entity type" value={f.entity_type} onChange={(e) => setF({ ...f, entity_type: e.target.value })} /></div>
        <div className="w-32"><Input label="Entity ID" value={f.entity_id} onChange={(e) => setF({ ...f, entity_id: e.target.value })} /></div>
      </div>
      {isLoading ? <Loading /> : (
        <Table head={["When", "Actor", "Action", "Entity", "Change", "Reason"]} empty={!rows.length}>
          {rows.map((a) => (
            <tr key={a.id}>
              <Td className="text-xs">{dateTime(a.created_at)}<br />{a.ip}</Td><Td>{a.actor}</Td><Td className="font-mono text-xs">{a.action}</Td><Td>{a.entity_type} #{a.entity_id}</Td>
              <Td><div className="grid gap-1 md:grid-cols-2"><Json value={a.before} /><Json value={a.after} /></div></Td><Td>{a.reason}</Td>
            </tr>
          ))}
        </Table>
      )}
      {pager}
    </div>
  );
}
