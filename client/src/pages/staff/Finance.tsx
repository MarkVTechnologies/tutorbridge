import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Alert, Button, Card, ErrorAlert, Input, Loading, Modal, PageHeader, Select, Stat, StatusBadge, Table, Td } from "@/components/ui";
import { api } from "@/lib/api";
import { hasPerm, useAuth } from "@/lib/auth";
import { dateTime, naira } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";

import { Json, usePaged } from "./common";

type Summary = {
  accounts: Record<string, { label: string; balance_kobo: number }>;
  trial_balance: { debits_kobo: number; credits_kobo: number; balanced: boolean };
  last_reconciliation: { run_date: string; checked: number; mismatches: unknown[]; created_at: string } | null;
};
type PayRow = { reference: string; parent: string; amount_kobo: number; fee_kobo: number; status: string; gateway: string; channel: string; booking: number | null; created_at: string };

export function Finance() {
  const { me } = useAuth();
  const { data, isLoading } = useApi<Summary>("/staff/finance/", ["finance"]);
  const [status, setStatus] = useState("");
  const payments = usePaged<PayRow>("/staff/finance/payments/", { status });
  const reconcile = useAction(() => api.post("/staff/finance/reconcile/"), [["finance"]]);
  if (isLoading || !data) return <Loading />;
  const exports = ["payments", "ledger", "payouts", "bookings", "lessons", "users"];
  return (
    <div className="space-y-6">
      <PageHeader title="Finance" subtitle="All balances are derived from the append-only double-entry ledger."
        actions={<Button variant="secondary" loading={reconcile.isPending} onClick={() => reconcile.mutate()}>Run reconciliation now</Button>} />
      {!data.trial_balance.balanced && <Alert title="Ledger out of balance">Debits {naira(data.trial_balance.debits_kobo)} ≠ credits {naira(data.trial_balance.credits_kobo)}. Investigate immediately.</Alert>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Object.entries(data.accounts).map(([k, a]) => <Stat key={k} label={a.label} value={naira(a.balance_kobo)} />)}
      </div>
      <Card title="Last reconciliation">
        {data.last_reconciliation ? (
          <>
            <p className="text-sm">{dateTime(data.last_reconciliation.created_at)} · {data.last_reconciliation.checked} payments checked · {data.last_reconciliation.mismatches.length} issue(s)</p>
            {data.last_reconciliation.mismatches.length > 0 && <Json value={data.last_reconciliation.mismatches} />}
          </>
        ) : <p className="text-sm text-slate-500">Not run yet.</p>}
      </Card>
      {hasPerm(me, "reports.export") && (
        <Card title="Exports (CSV, opens in Excel)">
          <div className="flex flex-wrap gap-2">{exports.map((e) => <a key={e} className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium hover:bg-slate-50" href={`/api/staff/exports/${e}/`}>{e}</a>)}</div>
        </Card>
      )}
      <Card title="Payments" actions={<div className="w-40"><Select label="Status" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option><option>success</option><option>initiated</option><option>failed</option><option>abandoned</option></Select></div>}>
        <Table head={["Date", "Reference", "Parent", "Amount", "Fee", "Channel", "Status"]} empty={!payments.rows.length}>
          {payments.rows.map((p) => (
            <tr key={p.reference}><Td>{dateTime(p.created_at)}</Td><Td className="font-mono text-xs">{p.reference}</Td><Td>{p.parent}</Td><Td>{naira(p.amount_kobo)}</Td><Td>{naira(p.fee_kobo)}</Td><Td>{p.gateway}/{p.channel || "—"}</Td><Td><StatusBadge status={p.status} /></Td></tr>
          ))}
        </Table>
        {payments.pager}
      </Card>
    </div>
  );
}

type PayoutRow = { id: number; status: string; total_kobo: number; created_at: string; created_by: string; approved_by: string | null; items: number };

export function Payouts() {
  const { me } = useAuth();
  const { rows, isLoading, pager } = usePaged<PayoutRow>("/staff/payouts/");
  const create = useAction(() => api.post<{ id: number }>("/staff/payouts/"), [["/staff/payouts/"]]);
  return (
    <div>
      <PageHeader title="Payouts" subtitle="Weekly batches are prepared automatically on Thursday evening. A different finance officer must approve each batch."
        actions={hasPerm(me, "payouts.create") && <Button variant="secondary" loading={create.isPending} onClick={() => create.mutate()}>Prepare batch now</Button>} />
      <ErrorAlert error={create.error} />
      {isLoading ? <Loading /> : (
        <Table head={["Batch", "Created", "Prepared by", "Items", "Total", "Approved by", "Status"]} empty={!rows.length}>
          {rows.map((p) => (
            <tr key={p.id}>
              <Td><Link className="font-medium text-brand-700" to={`/staff/payouts/${p.id}`}>#{p.id}</Link></Td><Td>{dateTime(p.created_at)}</Td><Td>{p.created_by}</Td>
              <Td>{p.items}</Td><Td>{naira(p.total_kobo)}</Td><Td>{p.approved_by ?? "—"}</Td><Td><StatusBadge status={p.status} /></Td>
            </tr>
          ))}
        </Table>
      )}
      {pager}
    </div>
  );
}

type PayoutDetailT = PayoutRow & { approved_at: string | null; items: { id: number; tutor: string; tutor_id: number; amount_kobo: number; bank: { bank_name: string; last4: string; account_name: string }; status: string; failure_reason: string; reference: string }[] };

export function PayoutDetail() {
  const { id } = useParams();
  const { me } = useAuth();
  const key = ["payout", id];
  const { data: p, isLoading } = useApi<PayoutDetailT>(`/staff/payouts/${id}/`, key);
  const [totp, setTotp] = useState("");
  const [approving, setApproving] = useState(false);
  const [retry, setRetry] = useState<number | null>(null);
  const approve = useAction(() => api.post(`/staff/payouts/${id}/approve/`, { totp }), [key]);
  const itemAction = useAction((a: { id: number; op: string }) => api.post(`/staff/payout-items/${a.id}/${a.op}/`, { totp }), [key]);
  if (isLoading || !p) return <Loading />;
  const isDraft = p.status === "draft";
  return (
    <div className="space-y-6">
      <PageHeader title={`Payout batch #${p.id}`} subtitle={<><StatusBadge status={p.status} /> · {naira(p.total_kobo)} · prepared by {p.created_by}</>} back={{ to: "/staff/payouts", label: "Payouts" }}
        actions={isDraft && hasPerm(me, "payouts.approve") && <Button onClick={() => setApproving(true)}>Approve & send</Button>} />
      {p.approved_by && <Alert tone="green">Approved by {p.approved_by} on {dateTime(p.approved_at)}.</Alert>}
      <Table head={["Tutor", "Amount", "Bank", "Status", "Reference", ""]} empty={!p.items.length}>
        {p.items.map((i) => (
          <tr key={i.id}>
            <Td>{i.tutor} <span className="text-xs text-slate-500">#{i.tutor_id}</span></Td>
            <Td>{naira(i.amount_kobo)}</Td>
            <Td className="text-xs">{i.bank.bank_name} ····{i.bank.last4}<br />{i.bank.account_name}</Td>
            <Td><StatusBadge status={i.status} />{i.failure_reason && <p className="text-xs text-red-600">{i.failure_reason}</p>}</Td>
            <Td className="font-mono text-xs">{i.reference}</Td>
            <Td>
              {isDraft && i.status === "pending" && hasPerm(me, "payouts.create") && <Button variant="ghost" onClick={() => itemAction.mutate({ id: i.id, op: "remove" })}>Remove</Button>}
              {i.status === "failed" && hasPerm(me, "payouts.create") && <Button variant="ghost" onClick={() => setRetry(i.id)}>Retry</Button>}
            </Td>
          </tr>
        ))}
      </Table>
      <Modal open={approving} onClose={() => setApproving(false)} title="Approve payout batch"
        footer={<Button loading={approve.isPending} onClick={() => approve.mutate(undefined, { onSuccess: () => setApproving(false) })}>Approve {naira(p.total_kobo)}</Button>}>
        <p className="text-sm text-slate-600">Transfers will be sent to {p.items.filter((i) => i.status === "pending").length} verified bank accounts. You cannot approve a batch you prepared.</p>
        <ErrorAlert error={approve.error} />
        <Input label="Authenticator code" inputMode="numeric" maxLength={6} value={totp} onChange={(e) => setTotp(e.target.value)} />
      </Modal>
      <Modal open={retry !== null} onClose={() => setRetry(null)} title="Retry transfer"
        footer={<Button loading={itemAction.isPending} onClick={() => itemAction.mutate({ id: retry!, op: "retry" }, { onSuccess: () => setRetry(null) })}>Retry</Button>}>
        <ErrorAlert error={itemAction.error} />
        <Input label="Authenticator code" inputMode="numeric" maxLength={6} value={totp} onChange={(e) => setTotp(e.target.value)} />
      </Modal>
    </div>
  );
}
