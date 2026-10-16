import { Plus, Tag } from "lucide-react";
import { useState } from "react";

import { Badge, Button, Card, Checkbox, EmptyState, ErrorAlert, Input, Loading, Modal, PageHeader, Select, Table, Td } from "@/components/ui";
import { api } from "@/lib/api";
import { dateOnly, naira, toKobo } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";

type Promo = {
  id: number; code: string; description: string; kind: "percent" | "fixed"; value: number; max_discount_kobo: number | null; min_spend_kobo: number;
  first_booking_only: boolean; packages_only: boolean; valid_from: string | null; valid_until: string | null; max_uses: number | null;
  max_uses_per_parent: number; is_active: boolean; uses: number; discount_given_kobo: number; created_at: string;
};

const blank = { code: "", description: "", kind: "percent", value: "", max_discount: "", min_spend: "", max_uses: "", max_uses_per_parent: "1", valid_until: "", first_booking_only: false, packages_only: false };

export function Promos() {
  const { data, isLoading } = useApi<Promo[]>("/staff/promos/", ["promos"]);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState(blank);
  const create = useAction(() => api.post("/staff/promos/", {
    code: f.code, description: f.description, kind: f.kind,
    value: f.kind === "percent" ? Number(f.value) : toKobo(f.value),
    max_discount_kobo: f.max_discount ? toKobo(f.max_discount) : null, min_spend_kobo: f.min_spend ? toKobo(f.min_spend) : 0,
    max_uses: f.max_uses ? Number(f.max_uses) : null, max_uses_per_parent: Number(f.max_uses_per_parent || 1),
    valid_until: f.valid_until ? new Date(f.valid_until).toISOString() : null, first_booking_only: f.first_booking_only, packages_only: f.packages_only,
  }), [["promos"]], { success: "Promo code created" });
  const toggle = useAction((p: Promo) => api.patch(`/staff/promos/${p.id}/`, { is_active: !p.is_active }), [["promos"]]);
  const totalGiven = data?.reduce((s, p) => s + p.discount_given_kobo, 0) ?? 0;
  return (
    <div>
      <PageHeader eyebrow="Marketing" title="Promo codes" subtitle={`Discounts are funded by TutorBridge — tutors are always paid in full. ${naira(totalGiven)} given so far.`}
        actions={<Button icon={Plus} onClick={() => { setF(blank); setOpen(true); }}>New promo code</Button>} />
      {isLoading ? <Loading /> : !data?.length ? (
        <EmptyState icon={Tag} title="No promo codes yet" action={<Button icon={Plus} onClick={() => setOpen(true)}>Create one</Button>}>Run an exam-season campaign or a welcome offer for new families.</EmptyState>
      ) : (
        <Table head={["Code", "Discount", "Rules", "Uses", "Given", "Status", ""]}>
          {data.map((p) => (
            <tr key={p.id}>
              <Td><span className="font-mono font-semibold text-ink-900">{p.code}</span>{p.description && <p className="text-xs text-ink-500">{p.description}</p>}</Td>
              <Td>{p.kind === "percent" ? `${p.value}%` : naira(p.value)}{p.max_discount_kobo ? <p className="text-xs text-ink-500">max {naira(p.max_discount_kobo)}</p> : null}</Td>
              <Td className="space-x-1 text-xs">
                {p.first_booking_only && <Badge>First booking</Badge>}
                {p.packages_only && <Badge>Packages only</Badge>}
                {p.min_spend_kobo > 0 && <Badge>Min {naira(p.min_spend_kobo)}</Badge>}
                {p.valid_until && <Badge tone="amber">Until {dateOnly(p.valid_until)}</Badge>}
              </Td>
              <Td>{p.uses}{p.max_uses ? ` / ${p.max_uses}` : ""}</Td>
              <Td>{naira(p.discount_given_kobo)}</Td>
              <Td>{p.is_active ? <Badge tone="green" dot>Active</Badge> : <Badge dot>Paused</Badge>}</Td>
              <Td><Button size="sm" variant="ghost" onClick={() => toggle.mutate(p)}>{p.is_active ? "Pause" : "Resume"}</Button></Td>
            </tr>
          ))}
        </Table>
      )}
      <Modal open={open} onClose={() => setOpen(false)} title="New promo code"
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button loading={create.isPending} onClick={() => create.mutate(undefined, { onSuccess: () => setOpen(false) })}>Create</Button></>}>
        <ErrorAlert error={create.error} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Code" placeholder="WAEC25" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} error={create.error?.field("code")} />
          <Select label="Type" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="percent">Percentage off</option><option value="fixed">Fixed amount off</option></Select>
          <Input label={f.kind === "percent" ? "Percent off" : "Amount off (₦)"} inputMode="numeric" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} error={create.error?.field("value")} />
          {f.kind === "percent" && <Input label="Maximum discount (₦, optional)" inputMode="numeric" value={f.max_discount} onChange={(e) => setF({ ...f, max_discount: e.target.value })} />}
          <Input label="Minimum spend (₦, optional)" inputMode="numeric" value={f.min_spend} onChange={(e) => setF({ ...f, min_spend: e.target.value })} />
          <Input label="Total uses (blank = unlimited)" inputMode="numeric" value={f.max_uses} onChange={(e) => setF({ ...f, max_uses: e.target.value })} />
          <Input label="Uses per family" inputMode="numeric" value={f.max_uses_per_parent} onChange={(e) => setF({ ...f, max_uses_per_parent: e.target.value })} />
          <Input label="Expires (optional)" type="datetime-local" value={f.valid_until} onChange={(e) => setF({ ...f, valid_until: e.target.value })} />
        </div>
        <Input label="Internal description" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
        <Checkbox label="First booking only" checked={f.first_booking_only} onChange={(e) => setF({ ...f, first_booking_only: e.target.checked })} />
        <Checkbox label="Packages only (not single trial lessons)" checked={f.packages_only} onChange={(e) => setF({ ...f, packages_only: e.target.checked })} />
      </Modal>
      <Card className="mt-6" title="Referral programme">
        <p className="text-sm text-ink-600">Every parent and tutor has a referral link. When a referred family completes their first package, both sides get a credit (set the amount under <strong>Settings → Referral credit</strong>). Costs appear in Finance under <em>Promotions &amp; referrals expense</em>.</p>
      </Card>
    </div>
  );
}
