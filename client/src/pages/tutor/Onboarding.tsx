import { useQueryClient } from "@tanstack/react-query";
import { Check, Send } from "lucide-react";
import { motion } from "@/lib/motion";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Seo } from "@/components/Seo";
import { FileUpload } from "@/components/shared";
import { Alert, Badge, Button, Card, Checkbox, ErrorAlert, Input, Loading, PageHeader, Select, StatusBadge, Textarea, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { WEEKDAYS, dateTime, naira, toKobo } from "@/lib/format";
import { useAction, useApi, useRefData } from "@/lib/hooks";
import type { TutorSubject } from "@/lib/types";

type Step = { key: string; label: string; done: boolean };
type Profile = {
  status: string; headline: string; bio: string; photo_url: string | null; highest_qualification: string; years_experience: number; trcn_number: string;
  curricula: number[]; hourly_rate_kobo: number; home_area: number | null; max_travel_km: number; accepts_special_needs: boolean; offers_online: boolean;
  subjects: TutorSubject[]; availability: { weekday: number; start_time: string; end_time: string }[]; areas: { id: number; name: string }[];
  progress: { steps: Step[]; completed: number; total: number; can_submit: boolean; police_certificate_uploaded: boolean };
  rate_band: { min_kobo: number; max_kobo: number } | null; location_consent: boolean;
};

const PROFILE_KEY = ["tutor-profile"];

export function Onboarding() {
  const [params, setParams] = useSearchParams();
  const { me } = useAuth();
  const { data: p, isLoading } = useApi<Profile>("/tutor/profile/", PROFILE_KEY);
  const submit = useAction(() => api.post("/tutor/submit/"), [PROFILE_KEY]);
  const current = params.get("step") ?? p?.progress.steps.find((s) => !s.done)?.key ?? "profile";
  if (isLoading || !p) return <Loading />;
  const steps = p.progress.steps;
  const idx = steps.findIndex((s) => s.key === current);
  const go = (key: string) => setParams({ step: key });
  const next = () => idx < steps.length - 1 && go(steps[idx + 1].key);
  const applied = p.status === "applied";
  const pct = Math.round((p.progress.completed / p.progress.total) * 100);
  return (
    <div>
      <Seo title="Profile & vetting" />
      <PageHeader eyebrow="Your application" title="Profile & vetting"
        subtitle={applied ? "Complete every step, then submit. Your progress saves as you go." : <span className="flex items-center gap-2">Status: <StatusBadge status={p.status} /></span>} />
      <div className="grid gap-8 lg:grid-cols-[18rem_1fr]">
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="rounded-3xl border border-ink-100 bg-white p-5 shadow-soft">
            <div className="flex items-center gap-4">
              <ProgressRing pct={pct} />
              <div>
                <p className="font-display text-lg font-bold text-ink-950">{p.progress.completed} of {p.progress.total}</p>
                <p className="text-sm text-ink-500">steps complete</p>
              </div>
            </div>
            <nav aria-label="Application steps" className="mt-5">
              <ol className="relative space-y-0.5">
                {steps.map((s, i) => (
                  <li key={s.key}>
                    <button onClick={() => go(s.key)} aria-current={s.key === current ? "step" : undefined}
                      className={cx("flex w-full items-center gap-3 rounded-xl px-2.5 py-2 text-left text-sm transition", s.key === current ? "bg-brand-50 font-semibold text-brand-800" : "text-ink-600 hover:bg-ink-50")}>
                      <span className={cx("flex size-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold transition",
                        s.done ? "bg-brand-600 text-white" : s.key === current ? "bg-gold-300 text-ink-950" : "bg-ink-100 text-ink-500")}>
                        {s.done ? <Check className="size-3.5" strokeWidth={3} /> : i + 1}
                      </span>
                      {s.label}
                    </button>
                  </li>
                ))}
              </ol>
            </nav>
            {applied && (
              <div className="mt-5 border-t border-ink-100 pt-5">
                <Button className="w-full" icon={Send} disabled={!p.progress.can_submit || !me?.is_verified} loading={submit.isPending} onClick={() => submit.mutate()}>Submit application</Button>
                {!me?.is_verified && <p className="mt-2 text-xs text-amber-700">Verify your email and phone first.</p>}
                {me?.is_verified && !p.progress.can_submit && <p className="mt-2 text-xs text-ink-500">Complete every step to submit.</p>}
                <div className="mt-3"><ErrorAlert error={submit.error} /></div>
              </div>
            )}
          </div>
        </aside>
        <motion.div key={current} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.25 }}>
          {current === "profile" && <ProfileStep p={p} onDone={next} />}
          {current === "subjects" && <SubjectsStep p={p} onDone={next} />}
          {current === "areas" && <AreasStep p={p} onDone={next} />}
          {current === "availability" && <AvailabilityStep p={p} onDone={next} />}
          {current === "rate" && <RateStep p={p} onDone={next} />}
          {current === "documents" && <DocumentsStep p={p} />}
          {current === "identity" && <IdentityStep />}
          {current === "bank" && <BankAccountCard />}
          {current === "tests" && <TestsStep />}
          {current === "interview" && <InterviewStep />}
          {current === "references" && <ReferencesStep />}
          {current === "safeguarding" && <SafeguardingStep />}
        </motion.div>
      </div>
    </div>
  );
}

function ProgressRing({ pct }: { pct: number }) {
  const r = 26, c = 2 * Math.PI * r;
  return (
    <div className="relative size-16">
      <svg viewBox="0 0 64 64" className="size-16 -rotate-90">
        <circle cx="32" cy="32" r={r} fill="none" stroke="var(--color-ink-100)" strokeWidth="7" />
        <motion.circle cx="32" cy="32" r={r} fill="none" stroke="url(#ring)" strokeWidth="7" strokeLinecap="round" strokeDasharray={c}
          initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - pct / 100) }} transition={{ duration: 1, ease: "easeOut" }} />
        <defs><linearGradient id="ring"><stop offset="0" stopColor="#1d8a60" /><stop offset="1" stopColor="#f9a325" /></linearGradient></defs>
      </svg>
      <span className="absolute inset-0 flex items-center justify-center font-display text-sm font-bold">{pct}%</span>
    </div>
  );
}

function useSaveProfile() {
  return useAction((body: Record<string, unknown>) => api.patch("/tutor/profile/", body), [PROFILE_KEY]);
}

function ProfileStep({ p, onDone }: { p: Profile; onDone: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ headline: p.headline, bio: p.bio, highest_qualification: p.highest_qualification, years_experience: p.years_experience, trcn_number: p.trcn_number, accepts_special_needs: p.accepts_special_needs, offers_online: p.offers_online });
  const save = useSaveProfile();
  return (
    <Card title="Personal details">
      <div className="space-y-4">
        <div className="flex items-center gap-4">
          {p.photo_url ? <img src={p.photo_url} alt="Your profile photo" className="h-20 w-20 rounded-full object-cover" /> : <div className="h-20 w-20 rounded-full bg-slate-200" />}
          <div>
            <FileUpload label={p.photo_url ? "Change photo" : "Upload photo"} accept=".jpg,.jpeg,.png" onUpload={async (file) => {
              const fd = new FormData(); fd.append("file", file);
              await api.post("/tutor/profile/photo/", fd);
              await qc.invalidateQueries({ queryKey: PROFILE_KEY });
            }} />
            <p className="mt-1 text-xs text-slate-500">A clear, friendly head-and-shoulders photo. Shown to families.</p>
          </div>
        </div>
        <ErrorAlert error={save.error} />
        <Input label="Headline" maxLength={120} placeholder="e.g. Physics graduate and WAEC/JAMB specialist" value={f.headline} onChange={(e) => setF({ ...f, headline: e.target.value })} />
        <Textarea label="About you" hint="Your teaching experience, approach and results. Don't include phone numbers, emails or social handles." value={f.bio} onChange={(e) => setF({ ...f, bio: e.target.value })} />
        <div className="grid gap-3 sm:grid-cols-3">
          <Input label="Highest qualification" value={f.highest_qualification} onChange={(e) => setF({ ...f, highest_qualification: e.target.value })} />
          <Input label="Years teaching" type="number" min={0} value={f.years_experience} onChange={(e) => setF({ ...f, years_experience: Number(e.target.value) })} />
          <Input label="TRCN number (if any)" value={f.trcn_number} onChange={(e) => setF({ ...f, trcn_number: e.target.value })} />
        </div>
        <Checkbox label="I have experience supporting children with special learning needs" checked={f.accepts_special_needs} onChange={(e) => setF({ ...f, accepts_special_needs: e.target.checked })} />
        <Checkbox label="I can also teach online" checked={f.offers_online} onChange={(e) => setF({ ...f, offers_online: e.target.checked })} />
        <Button loading={save.isPending} onClick={() => save.mutate(f, { onSuccess: onDone })}>Save and continue</Button>
      </div>
    </Card>
  );
}

function SubjectsStep({ p, onDone }: { p: Profile; onDone: () => void }) {
  const { data: ref } = useRefData();
  const [items, setItems] = useState<Set<string>>(new Set(p.subjects.map((s) => `${s.subject}:${s.level}`)));
  const [curricula, setCurricula] = useState<number[]>(p.curricula);
  const [filter, setFilter] = useState("");
  const save = useAction(() => api.put("/tutor/profile/subjects/", { items: [...items].map((k) => { const [subject, level] = k.split(":").map(Number); return { subject, level }; }), curricula }), [PROFILE_KEY]);
  const toggle = (k: string) => setItems((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  const subjects = ref?.subjects.filter((s) => s.name.toLowerCase().includes(filter.toLowerCase())) ?? [];
  return (
    <Card title="Subjects & levels">
      <p className="mb-3 text-sm text-slate-600">Tick every subject and level you can teach confidently. You'll take a short test for each.</p>
      <fieldset className="mb-4">
        <legend className="mb-2 text-sm font-medium">Curricula</legend>
        <div className="flex flex-wrap gap-3">
          {ref?.curricula.map((c) => <Checkbox key={c.id} label={c.name} checked={curricula.includes(c.id)} onChange={(e) => setCurricula(e.target.checked ? [...curricula, c.id] : curricula.filter((x) => x !== c.id))} />)}
        </div>
      </fieldset>
      <Input label="Filter subjects" value={filter} onChange={(e) => setFilter(e.target.value)} />
      <div className="mt-3 overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead><tr><th className="py-2 text-left">Subject</th>{ref?.levels.map((l) => <th key={l.id} className="px-2 py-2 text-center font-medium">{l.name}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100">
            {subjects.map((s) => (
              <tr key={s.id}>
                <td className="py-2 pr-3">{s.name}</td>
                {ref?.levels.map((l) => {
                  const k = `${s.id}:${l.id}`;
                  return <td key={l.id} className="text-center"><input type="checkbox" aria-label={`${s.name} ${l.name}`} className="h-5 w-5" checked={items.has(k)} onChange={() => toggle(k)} /></td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ErrorAlert error={save.error} />
      <Button className="mt-4" loading={save.isPending} disabled={!items.size || !curricula.length} onClick={() => save.mutate(undefined, { onSuccess: onDone })}>Save and continue</Button>
    </Card>
  );
}

function AreasStep({ p, onDone }: { p: Profile; onDone: () => void }) {
  const { data: ref } = useRefData();
  const [home, setHome] = useState(p.home_area ?? "");
  const [areas, setAreas] = useState<number[]>(p.areas.map((a) => a.id));
  const [km, setKm] = useState(p.max_travel_km);
  const save = useAction(() => api.put("/tutor/profile/areas/", { home_area: Number(home), areas, max_travel_km: km }), [PROFILE_KEY]);
  const byLga = useMemo(() => ref?.lgas.map((l) => ({ lga: l, areas: ref.areas.filter((a) => a.lga_id === l.id) })).filter((g) => g.areas.length) ?? [], [ref]);
  return (
    <Card title="Areas you serve">
      <div className="space-y-4">
        <Select label="Where do you live? (neighbourhood)" value={home} onChange={(e) => setHome(e.target.value)} hint="Used to calculate travel distance. Never shown in full.">
          <option value="">Choose…</option>{ref?.areas.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </Select>
        <Input label="Maximum travel distance (km)" type="number" min={1} max={50} value={km} onChange={(e) => setKm(Number(e.target.value))} />
        {byLga.map(({ lga, areas: list }) => (
          <fieldset key={lga.id}>
            <legend className="text-sm font-semibold text-slate-700">{lga.name}</legend>
            <div className="mt-1 flex flex-wrap gap-3">
              {list.map((a) => <Checkbox key={a.id} label={a.name} checked={areas.includes(a.id)} onChange={(e) => setAreas(e.target.checked ? [...areas, a.id] : areas.filter((x) => x !== a.id))} />)}
            </div>
          </fieldset>
        ))}
        <ErrorAlert error={save.error} />
        <Button loading={save.isPending} disabled={!home || !areas.length} onClick={() => save.mutate(undefined, { onSuccess: onDone })}>Save and continue</Button>
      </div>
    </Card>
  );
}

function AvailabilityStep({ p, onDone }: { p: Profile; onDone: () => void }) {
  const [slots, setSlots] = useState(p.availability.map((a) => ({ ...a, start_time: a.start_time.slice(0, 5), end_time: a.end_time.slice(0, 5) })));
  const save = useAction(() => api.put("/tutor/profile/availability/", { slots }), [PROFILE_KEY]);
  return (
    <Card title="Weekly availability">
      <p className="mb-4 text-sm text-slate-600">When can you teach each week? Add one or more time ranges per day. Families are matched to these times.</p>
      <div className="space-y-3">
        {WEEKDAYS.map((d, wd) => (
          <div key={d} className="flex flex-wrap items-center gap-2">
            <span className="w-24 text-sm font-medium">{d}</span>
            {slots.map((s, i) => s.weekday === wd && (
              <span key={i} className="flex items-center gap-1 rounded-lg bg-slate-100 px-2 py-1">
                <input type="time" aria-label={`${d} from`} className="rounded border-slate-300 text-sm" value={s.start_time} onChange={(e) => setSlots(slots.map((x, j) => (j === i ? { ...x, start_time: e.target.value } : x)))} />
                –
                <input type="time" aria-label={`${d} to`} className="rounded border-slate-300 text-sm" value={s.end_time} onChange={(e) => setSlots(slots.map((x, j) => (j === i ? { ...x, end_time: e.target.value } : x)))} />
                <button aria-label="Remove" className="px-1 text-slate-500" onClick={() => setSlots(slots.filter((_, j) => j !== i))}>✕</button>
              </span>
            ))}
            <Button variant="ghost" onClick={() => setSlots([...slots, { weekday: wd, start_time: "16:00", end_time: "19:00" }])}>+ Add</Button>
          </div>
        ))}
      </div>
      <ErrorAlert error={save.error} />
      <Button className="mt-4" loading={save.isPending} disabled={!slots.length} onClick={() => save.mutate(undefined, { onSuccess: onDone })}>Save and continue</Button>
    </Card>
  );
}

function RateStep({ p, onDone }: { p: Profile; onDone: () => void }) {
  const [rate, setRate] = useState(p.hourly_rate_kobo ? String(p.hourly_rate_kobo / 100) : "");
  const save = useSaveProfile();
  return (
    <Card title="Hourly rate">
      {p.rate_band ? (
        <p className="mb-3 text-sm text-slate-600">For the levels you teach, set a rate between <strong>{naira(p.rate_band.min_kobo)}</strong> and <strong>{naira(p.rate_band.max_kobo)}</strong> per hour. This is the price families see.</p>
      ) : <Alert tone="amber">Choose your subjects and levels first.</Alert>}
      <div className="w-56"><Input label="Rate per hour (₦)" inputMode="numeric" value={rate} onChange={(e) => setRate(e.target.value)} error={save.error?.field("hourly_rate_kobo")} /></div>
      <p className="mt-2 text-sm text-slate-500">TutorBridge commission is 20% (lower for Gold and Elite tutors). At {naira(toKobo(rate || 0))}/hour you'd earn {naira(Math.round(toKobo(rate || 0) * 0.8))} per hour.</p>
      <Button className="mt-4" loading={save.isPending} disabled={!p.rate_band || !rate} onClick={() => save.mutate({ hourly_rate_kobo: toKobo(rate) }, { onSuccess: onDone })}>Save and continue</Button>
    </Card>
  );
}

type Doc = { id: number; doc_type: string; doc_type_display: string; original_name: string; status: string; review_note: string };
const DOCS: [string, string, boolean][] = [
  ["cv", "CV", true], ["degree", "Degree certificate", false], ["nce", "NCE certificate", false], ["trcn", "TRCN certificate", false],
  ["certificate", "Other certificates", false], ["proof_of_address", "Proof of address (utility bill, tenancy)", true], ["police_certificate", "Police character certificate", false],
];

function DocumentsStep({ p }: { p: Profile }) {
  const qc = useQueryClient();
  const { data: docs } = useApi<Doc[]>("/vetting/documents/", ["documents"]);
  const remove = useAction((id: number) => api.del(`/vetting/documents/${id}/`), [["documents"], PROFILE_KEY]);
  const upload = async (doc_type: string, file: File) => {
    const fd = new FormData(); fd.append("doc_type", doc_type); fd.append("file", file);
    await api.post("/vetting/documents/", fd);
    await qc.invalidateQueries({ queryKey: ["documents"] });
    await qc.invalidateQueries({ queryKey: PROFILE_KEY });
  };
  return (
    <Card title="Documents">
      <p className="mb-4 text-sm text-slate-600">PDF, JPG or PNG, up to 5 MB each. Files are stored privately and only seen by our vetting team. You need a CV, a degree <em>or</em> NCE certificate, and proof of address to submit.</p>
      {!p.progress.police_certificate_uploaded && <Alert tone="blue">A police character certificate is required before your first home visit. You can submit your application without it and upload it later.</Alert>}
      <ul className="mt-4 divide-y divide-slate-100">
        {DOCS.map(([type, label, required]) => {
          const mine = docs?.filter((d) => d.doc_type === type) ?? [];
          return (
            <li key={type} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div>
                <p className="font-medium">{label} {required && <span className="text-red-600">*</span>}</p>
                {mine.map((d) => (
                  <p key={d.id} className="text-sm text-slate-600">
                    {d.original_name} <StatusBadge status={d.status} />
                    {d.review_note && <span className="text-red-600"> — {d.review_note}</span>}
                    {d.status === "pending" && <button className="ml-2 text-xs text-slate-500 underline" onClick={() => remove.mutate(d.id)}>remove</button>}
                  </p>
                ))}
              </div>
              <FileUpload label={mine.length ? "Upload another" : "Upload"} onUpload={(f) => upload(type, f)} />
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function IdentityStep() {
  const qc = useQueryClient();
  const { data } = useApi<{ status: string; notes: string }>("/vetting/identity/", ["identity"]);
  const [nin, setNin] = useState("");
  const [selfie, setSelfie] = useState<File | null>(null);
  const submit = useAction(async () => {
    const fd = new FormData(); fd.append("nin", nin); if (selfie) fd.append("selfie", selfie);
    await api.post("/vetting/identity/", fd);
    await qc.invalidateQueries({ queryKey: PROFILE_KEY });
  }, [["identity"]]);
  const st = data?.status ?? "pending";
  return (
    <Card title="NIN & selfie verification">
      {st === "passed" && <Alert tone="green">Your identity is verified.</Alert>}
      {(st === "submitted" || st === "manual_review") && <Alert tone="blue">Submitted. Our team is checking your NIN against your selfie.</Alert>}
      {st === "failed" && <Alert>Verification failed{data?.notes ? `: ${data.notes}` : ""}. Please contact support.</Alert>}
      {st === "pending" && (
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); submit.mutate(); }}>
          <p className="text-sm text-slate-600">We match your National Identification Number (NIN) to a live selfie through a licensed verification provider.</p>
          <ErrorAlert error={submit.error} />
          <Input label="NIN (11 digits)" inputMode="numeric" maxLength={11} required value={nin} onChange={(e) => setNin(e.target.value.replace(/\D/g, ""))} />
          <div>
            <label className="block text-sm font-medium text-slate-700">Selfie</label>
            <p className="text-xs text-slate-500">Face the camera in good light, no hat or sunglasses.</p>
            <input type="file" accept="image/jpeg,image/png" capture="user" className="mt-2 text-sm" onChange={(e) => setSelfie(e.target.files?.[0] ?? null)} required />
          </div>
          <Button type="submit" loading={submit.isPending}>Verify my identity</Button>
        </form>
      )}
    </Card>
  );
}

type Bank = { id: number; bank_name: string; account_last4: string; account_name: string; name_match: boolean; verified_at: string | null; payout_hold_until: string | null };

export function BankAccountCard() {
  const qc = useQueryClient();
  const current = useApi<Bank | null>("/bank-account/", ["bank"]);
  const [editing, setEditing] = useState(false);
  const banks = useApi<{ name: string; code: string }[]>(editing || current.data === null ? "/banks/" : null, ["banks"]);
  const [f, setF] = useState({ bank_code: "", account_number: "", code: "" });
  const changing = !!current.data?.verified_at;
  const sendOtp = useAction(() => api.post("/bank-account/otp/"));
  const save = useAction(async () => {
    const bank = banks.data?.find((b) => b.code === f.bank_code);
    await api.post("/bank-account/", { ...f, bank_name: bank?.name ?? "" });
    await qc.invalidateQueries({ queryKey: PROFILE_KEY });
  }, [["bank"]]);
  const b = current.data;
  const showForm = editing || b === null;
  return (
    <Card title="Bank account for payouts">
      {b && (
        <div className="space-y-2">
          <p className="font-medium">{b.bank_name} ····{b.account_last4} — {b.account_name}</p>
          {b.name_match ? <Badge tone="green">✓ Name matches your verified identity</Badge> : <Badge tone="amber">Name mismatch — under manual review</Badge>}
          {b.payout_hold_until && new Date(b.payout_hold_until) > new Date() && <Alert tone="amber">For your security, payouts to this new account are on hold until {dateTime(b.payout_hold_until)}.</Alert>}
          {!editing && <Button variant="secondary" onClick={() => setEditing(true)}>Change account</Button>}
        </div>
      )}
      {showForm && (
        <form className="mt-3 space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(undefined, { onSuccess: () => setEditing(false) }); }}>
          <p className="text-sm text-slate-600">The account must be in your own name. We check the name with your bank.</p>
          <ErrorAlert error={save.error} />
          <Select label="Bank" required value={f.bank_code} onChange={(e) => setF({ ...f, bank_code: e.target.value })}>
            <option value="">Choose…</option>{banks.data?.map((bk) => <option key={bk.code} value={bk.code}>{bk.name}</option>)}
          </Select>
          <Input label="Account number" inputMode="numeric" maxLength={10} required value={f.account_number} onChange={(e) => setF({ ...f, account_number: e.target.value.replace(/\D/g, "") })} error={save.error?.field("account_number")} />
          {changing && (
            <div className="flex flex-wrap items-end gap-2">
              <div className="w-40"><Input label="Security code" inputMode="numeric" maxLength={6} required value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} error={save.error?.field("code")} /></div>
              <Button type="button" variant="ghost" loading={sendOtp.isPending} onClick={() => sendOtp.mutate()}>{sendOtp.isSuccess ? "Code sent" : "Text me a code"}</Button>
            </div>
          )}
          {changing && <p className="text-xs text-slate-500">Changing your bank account puts payouts on hold for 48 hours.</p>}
          <div className="flex gap-2">
            <Button type="submit" loading={save.isPending}>Verify account</Button>
            {editing && <Button type="button" variant="secondary" onClick={() => setEditing(false)}>Cancel</Button>}
          </div>
        </form>
      )}
    </Card>
  );
}

type TestRow = { subject: number; subject_name: string; level: number; level_name: string; best_score: number | null; passed: boolean; attempts: number; available: boolean };
type Attempt = { id: number; deadline: string; questions: { id: number; text: string; options: string[] }[] };

function TestsStep() {
  const { data } = useApi<TestRow[]>("/vetting/tests/", ["tests"]);
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [result, setResult] = useState<{ score_pct: number; passed: boolean } | null>(null);
  const start = useAction((t: TestRow) => api.post<Attempt>("/vetting/tests/start/", { subject: t.subject, level: t.level }));
  if (attempt) return <TakeTest attempt={attempt} onDone={(r) => { setAttempt(null); setResult(r); }} />;
  return (
    <Card title="Subject tests">
      <p className="mb-3 text-sm text-slate-600">A timed multiple-choice test for each subject and level you teach. You can attempt each test twice a week.</p>
      {result && <Alert tone={result.passed ? "green" : "amber"}>You scored {result.score_pct}% — {result.passed ? "passed!" : "not quite. Review and try again."}</Alert>}
      <ErrorAlert error={start.error} />
      <ul className="mt-3 divide-y divide-slate-100">
        {data?.map((t) => (
          <li key={`${t.subject}-${t.level}`} className="flex flex-wrap items-center justify-between gap-2 py-3">
            <div>
              <p className="font-medium">{t.subject_name} — {t.level_name}</p>
              <p className="text-sm text-slate-500">{t.best_score !== null ? `Best score ${t.best_score}%` : "Not taken"} · {t.attempts} attempt(s)</p>
            </div>
            {t.passed ? <Badge tone="green">✓ Passed</Badge> : t.available ? (
              <Button loading={start.isPending} onClick={() => start.mutate(t, { onSuccess: setAttempt })}>Start test</Button>
            ) : <Badge tone="slate">Test coming soon — our team will review manually</Badge>}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function TakeTest({ attempt, onDone }: { attempt: Attempt; onDone: (r: { score_pct: number; passed: boolean }) => void }) {
  const qc = useQueryClient();
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [left, setLeft] = useState(() => Math.max(0, Math.floor((new Date(attempt.deadline).getTime() - Date.now()) / 1000)));
  const submit = useAction(() => api.post<{ score_pct: number; passed: boolean }>(`/vetting/tests/${attempt.id}/submit/`, { answers }), [["tests"], PROFILE_KEY]);
  useEffect(() => {
    const t = setInterval(() => setLeft((s) => s - 1), 1000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    if (left === 0 && !submit.isPending) submit.mutate(undefined, { onSuccess: onDone });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [left]);
  return (
    <Card title="Subject test" actions={<span className={cx("rounded px-2 py-1 font-mono", left < 120 ? "bg-red-100 text-red-700" : "bg-slate-100")}>{Math.floor(Math.max(left, 0) / 60)}:{String(Math.max(left, 0) % 60).padStart(2, "0")}</span>}>
      <ol className="space-y-6">
        {attempt.questions.map((q, i) => (
          <li key={q.id}>
            <fieldset>
              <legend className="font-medium">{i + 1}. {q.text}</legend>
              <div className="mt-2 space-y-1">
                {q.options.map((o, j) => (
                  <label key={j} className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-slate-50">
                    <input type="radio" name={`q${q.id}`} checked={answers[q.id] === j} onChange={() => setAnswers({ ...answers, [q.id]: j })} className="h-4 w-4" />
                    {o}
                  </label>
                ))}
              </div>
            </fieldset>
          </li>
        ))}
      </ol>
      <ErrorAlert error={submit.error} />
      <Button className="mt-6" loading={submit.isPending} onClick={() => submit.mutate(undefined, { onSuccess: async (r) => { await qc.invalidateQueries({ queryKey: ["tests"] }); onDone(r); } })}>
        Submit answers ({Object.keys(answers).length}/{attempt.questions.length})
      </Button>
    </Card>
  );
}

type Slots = { booked: { id: number; starts_at: string; duration_minutes: number; meeting_link: string; outcome: string } | null; available: { id: number; starts_at: string; duration_minutes: number }[] };

function InterviewStep() {
  const { data } = useApi<Slots>("/vetting/interview-slots/", ["interview"]);
  const book = useAction((id: number) => api.post(`/vetting/interview-slots/${id}/book/`), [["interview"], PROFILE_KEY]);
  return (
    <Card title="Video interview">
      <p className="mb-3 text-sm text-slate-600">A 30-minute video call with our vetting team: a short teaching demo, communication and safeguarding scenarios.</p>
      {data?.booked && !data.booked.outcome && (
        <Alert tone="green" title="Interview booked">{dateTime(data.booked.starts_at)}. {data.booked.meeting_link ? <a className="underline" href={data.booked.meeting_link} target="_blank" rel="noreferrer">Join link</a> : "We'll send the meeting link by email."}</Alert>
      )}
      {data?.booked?.outcome && <Alert tone={data.booked.outcome === "pass" ? "green" : "amber"}>Interview outcome: {data.booked.outcome}</Alert>}
      {!data?.booked && (
        <>
          <ErrorAlert error={book.error} />
          {data?.available.length === 0 && <p className="text-slate-500">No slots available right now — new slots are added daily. Check back soon.</p>}
          <div className="grid gap-2 sm:grid-cols-2">
            {data?.available.map((s) => <Button key={s.id} variant="secondary" loading={book.isPending} onClick={() => book.mutate(s.id)}>{dateTime(s.starts_at)}</Button>)}
          </div>
        </>
      )}
    </Card>
  );
}

type Ref = { id: number; kind: string; name: string; email: string; phone: string; relationship: string; organisation: string; is_professional: boolean; submitted_at: string | null };

function ReferencesStep() {
  const { data } = useApi<Ref[]>("/vetting/references/", ["references"]);
  const empty = { kind: "referee", name: "", email: "", phone: "", relationship: "", organisation: "", is_professional: false };
  const [f, setF] = useState(empty);
  const add = useAction(() => api.post("/vetting/references/", f), [["references"], PROFILE_KEY]);
  const referees = data?.filter((r) => r.kind === "referee") ?? [];
  const guarantor = data?.find((r) => r.kind === "guarantor");
  return (
    <Card title="Referees & guarantor">
      <p className="mb-3 text-sm text-slate-600">Two referees (at least one professional, e.g. a head teacher or employer) and one guarantor. We'll email each a secure form and may call them.</p>
      <ul className="mb-4 divide-y divide-slate-100">
        {data?.map((r) => (
          <li key={r.id} className="flex justify-between py-2 text-sm">
            <span><strong>{r.name}</strong> — {r.kind}{r.is_professional ? " (professional)" : ""}, {r.relationship}</span>
            {r.submitted_at ? <Badge tone="green">Responded</Badge> : <Badge tone="amber">Awaiting response</Badge>}
          </li>
        ))}
      </ul>
      {(referees.length < 2 || !guarantor) && (
        <form className="space-y-3 rounded-lg bg-slate-50 p-4" onSubmit={(e) => { e.preventDefault(); add.mutate(undefined, { onSuccess: () => setF(empty) }); }}>
          <ErrorAlert error={add.error} />
          <Select label="Type" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
            {referees.length < 3 && <option value="referee">Referee</option>}
            {!guarantor && <option value="guarantor">Guarantor</option>}
          </Select>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input label="Full name" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
            <Input label="Relationship to you" required value={f.relationship} onChange={(e) => setF({ ...f, relationship: e.target.value })} />
            <Input label="Email" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
            <Input label="Phone" type="tel" required value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />
            <Input label="Organisation (optional)" value={f.organisation} onChange={(e) => setF({ ...f, organisation: e.target.value })} />
          </div>
          {f.kind === "referee" && <Checkbox label="This is a professional referee (employer, head teacher, lecturer)" checked={f.is_professional} onChange={(e) => setF({ ...f, is_professional: e.target.checked })} />}
          <Button type="submit" loading={add.isPending}>Add and send form</Button>
        </form>
      )}
    </Card>
  );
}

type Safeguarding = { pages: { title: string; body: string }[]; quiz: { q: string; options: string[] }[]; agreement_version: string; completed_at: string | null; agreement_signed_at: string | null };

function SafeguardingStep() {
  const { me } = useAuth();
  const { data } = useApi<Safeguarding>("/vetting/safeguarding/", ["safeguarding"]);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [signature, setSignature] = useState("");
  const [agree, setAgree] = useState(false);
  const [location, setLocation] = useState(true);
  const submit = useAction(() => api.post("/vetting/safeguarding/", { answers, signature, location_consent: location }), [["safeguarding"], PROFILE_KEY]);
  if (!data) return <Loading />;
  if (data.agreement_signed_at) return <Card title="Safeguarding & agreement"><Alert tone="green">Completed and signed on {dateTime(data.agreement_signed_at)} (agreement version {data.agreement_version}).</Alert></Card>;
  return (
    <div className="space-y-4">
      {data.pages.map((p, i) => <Card key={i} title={`${i + 1}. ${p.title}`}><p className="text-slate-700">{p.body}</p></Card>)}
      <Card title="Quick check">
        <ol className="space-y-4">
          {data.quiz.map((q, i) => (
            <li key={i}>
              <fieldset>
                <legend className="font-medium">{q.q}</legend>
                {q.options.map((o, j) => (
                  <label key={j} className="mt-1 flex items-center gap-2">
                    <input type="radio" name={`sg${i}`} checked={answers[i] === j} onChange={() => setAnswers({ ...answers, [i]: j })} className="h-4 w-4" /> {o}
                  </label>
                ))}
              </fieldset>
            </li>
          ))}
        </ol>
      </Card>
      <Card title="Tutor agreement & code of conduct">
        <div className="space-y-2 text-sm text-slate-700">
          <p>As an independent contractor with TutorBridge, I agree to: follow the code of conduct above; keep all contact with families on the platform; not arrange lessons privately with families I meet through TutorBridge for 12 months after our last booking (non-circumvention); and accept that serious complaints lead to suspension pending investigation.</p>
        </div>
        <div className="mt-4 space-y-3">
          <Checkbox label="I have read and agree to the Tutor Agreement and Code of Conduct" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
          <Checkbox label="I consent to my approximate location being recorded when I check in to a lesson" checked={location} onChange={(e) => setLocation(e.target.checked)} />
          <Input label={`Type your full name to sign (${me?.first_name} ${me?.last_name})`} value={signature} onChange={(e) => setSignature(e.target.value)} error={submit.error?.field("signature")} />
          {submit.error && !submit.error.field("signature") && <ErrorAlert error={submit.error} />}
          <Button disabled={!agree || Object.keys(answers).length < data.quiz.length} loading={submit.isPending} onClick={() => submit.mutate()}>Sign agreement</Button>
        </div>
      </Card>
    </div>
  );
}
