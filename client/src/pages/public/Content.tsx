import { ArrowRight, BadgeCheck, Clock, FileText, Mail, MapPin, MessageSquare, Phone, Send, ShieldCheck, Siren, UserRound } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Prose } from "@/components/Layout";
import { CtaBand, FaqAccordion, PageHero } from "@/components/marketing";
import { Seo } from "@/components/Seo";
import { Alert, Button, ButtonLink, Card, EmptyState, ErrorAlert, IconTile, Input, Loading, Reveal, Select, Tabs, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { dateOnly, naira } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";

type Faq = { id: number; audience: string; question: string; answer: string };

export function Faq() {
  const { data, isLoading } = useApi<Faq[]>("/faqs/");
  const [aud, setAud] = useState<"parent" | "tutor" | "general">("parent");
  const items = data?.filter((f) => f.audience === aud).map((f) => ({ q: f.question, a: f.answer })) ?? [];
  return (
    <>
      <Seo title="Frequently asked questions" />
      <PageHero eyebrow="Help centre" title="Questions, answered." subtitle="Everything families and tutors ask us most." />
      <div className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
        <div className="mb-8 flex justify-center">
          <Tabs value={aud} onChange={setAud} options={[{ value: "parent", label: "Parents" }, { value: "tutor", label: "Tutors" }, { value: "general", label: "General" }]} />
        </div>
        {isLoading ? <Loading /> : items.length ? <FaqAccordion key={aud} items={items} /> : <EmptyState title="Nothing here yet" />}
        <p className="mt-10 text-center text-ink-500">Still stuck? <Link to="/contact" className="font-semibold text-brand-600 hover:underline">Contact our team</Link></p>
      </div>
    </>
  );
}

export function Contact() {
  const [form, setForm] = useState({ name: "", email: "", phone: "", topic: "general", message: "" });
  const [sent, setSent] = useState(false);
  const send = useAction(() => api.post("/contact/", form));
  return (
    <>
      <Seo title="Contact us" />
      <PageHero eyebrow="Contact" title="We'd love to hear from you." subtitle="We reply within one working day." />
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-14 sm:px-6 lg:grid-cols-[1fr_1.4fr]">
        <div className="space-y-4">
          {[[Mail, "Email", "hello@tutorbridge.ng", "green"], [MessageSquare, "Partnerships", "Schools, estates and employers — ask about bulk packages.", "gold"], [MapPin, "Where we are", "Lagos, Nigeria — Abuja and Port Harcourt next.", "blue"]].map(([I, t, d, tone]) => (
            <Reveal key={t as string}>
              <div className="flex gap-4 rounded-3xl border border-ink-100 bg-white p-5 shadow-soft">
                <IconTile icon={I as typeof Mail} tone={tone as "green"} />
                <div><p className="font-semibold text-ink-900">{t as string}</p><p className="text-sm text-ink-500">{d as string}</p></div>
              </div>
            </Reveal>
          ))}
          <div className="flex gap-4 rounded-3xl bg-red-50 p-5 ring-1 ring-red-200">
            <IconTile icon={Siren} tone="red" />
            <p className="text-sm text-red-900"><strong>Urgent safety concern during a lesson?</strong> Call 112 if anyone is in danger, then use the safety button on the lesson page.</p>
          </div>
        </div>
        <Card>
          {sent ? (
            <div className="py-10 text-center">
              <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} className="mx-auto flex size-16 items-center justify-center rounded-full bg-brand-500 text-white shadow-glow"><Send className="size-7" /></motion.div>
              <p className="mt-5 font-display text-2xl font-bold">Message sent</p>
              <p className="mt-1 text-ink-500">Thanks — we'll be in touch soon.</p>
            </div>
          ) : (
            <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); send.mutate(undefined, { onSuccess: () => setSent(true) }); }}>
              <ErrorAlert error={send.error} />
              <div className="grid gap-4 sm:grid-cols-2">
                <Input label="Name" icon={UserRound} required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                <Input label="Email" icon={Mail} type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
                <Input label="Phone (optional)" icon={Phone} type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
                <Select label="Topic" value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })}>
                  <option value="general">General</option><option value="parent">I'm a parent</option><option value="tutor">I'm a tutor</option><option value="partnership">Partnership</option>
                </Select>
              </div>
              <Textarea label="Message" required value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} />
              <Button type="submit" size="lg" icon={Send} loading={send.isPending}>Send message</Button>
            </form>
          )}
        </Card>
      </div>
    </>
  );
}

export function Blog() {
  const { data, isLoading } = useApi<{ slug: string; title: string; excerpt: string; published_at: string }[]>("/blog/");
  return (
    <>
      <Seo title="Blog" />
      <PageHero eyebrow="Blog" title="Study tips, exam countdowns and tutor spotlights" />
      <div className="mx-auto max-w-5xl px-4 py-14 sm:px-6">
        {isLoading && <Loading />}
        {data?.length === 0 && <EmptyState icon={FileText} title="First posts coming soon">We're writing guides for Common Entrance, BECE, WAEC and JAMB season.</EmptyState>}
        <div className="grid gap-5 md:grid-cols-2">
          {data?.map((p) => (
            <Link key={p.slug} to={`/blog/${p.slug}`} className="group rounded-3xl border border-ink-100 bg-white p-7 shadow-soft transition hover:-translate-y-1 hover:shadow-lift">
              <p className="text-xs font-semibold tracking-wider text-brand-600 uppercase">{dateOnly(p.published_at)}</p>
              <h2 className="mt-2 font-display text-2xl font-bold text-ink-950 group-hover:text-brand-700">{p.title}</h2>
              <p className="mt-2 text-ink-500">{p.excerpt}</p>
              <span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-brand-600">Read more <ArrowRight className="size-4 transition group-hover:translate-x-0.5" /></span>
            </Link>
          ))}
        </div>
      </div>
    </>
  );
}

export function BlogPost() {
  const { slug } = useParams();
  const { data, isLoading } = useApi<{ title: string; body: string; published_at: string }>(`/blog/${slug}/`);
  if (isLoading) return <Loading />;
  if (!data) return null;
  return (
    <>
      <Seo title={data.title} />
      <PageHero eyebrow={dateOnly(data.published_at)} title={data.title} />
      <article className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
        <Prose>{data.body.split(/\n{2,}/).map((p, i) => <p key={i}>{p}</p>)}</Prose>
      </article>
      <CtaBand title="Find a vetted tutor near you." subtitle="Shortlist within 24 hours." primary={{ to: "/signup?role=parent", label: "Request a tutor" }} />
    </>
  );
}

/** WEB-02: "<Subject> home tutor in <Area>" landing page. */
export function SeoLanding() {
  const { subject, area } = useParams();
  const { data, isLoading } = useApi<{ subject: string; area: string; tutor_count: number; from_rate_kobo: number | null }>(`/seo/${subject}/${area}/`);
  if (isLoading) return <Loading />;
  if (!data) return null;
  return (
    <>
      <Seo title={`${data.subject} home tutor in ${data.area}`} description={`Vetted ${data.subject} home tutors in ${data.area}, Lagos. ID-verified, background-checked and subject-tested.`} />
      <PageHero eyebrow={`${data.area}, Lagos`} title={`${data.subject} home tutors in ${data.area}`}
        subtitle={<>{data.tutor_count > 0 ? `${data.tutor_count} vetted ${data.subject} tutor${data.tutor_count > 1 ? "s" : ""} serve ${data.area}` : `We're recruiting ${data.subject} tutors in ${data.area}`}{data.from_rate_kobo ? `, from ${naira(data.from_rate_kobo)} per hour.` : "."}</>}>
        <div className="flex flex-wrap justify-center gap-3">
          <ButtonLink to={`/tutors?subject=${subject}&area=${area}`} size="lg" iconRight={ArrowRight}>See tutors</ButtonLink>
          <ButtonLink to="/signup?role=parent" size="lg" variant="secondary">Request a tutor</ButtonLink>
        </div>
      </PageHero>
      <div className="mx-auto grid max-w-5xl gap-5 px-4 py-14 sm:px-6 md:grid-cols-3">
        {[[ShieldCheck, "Every tutor vetted", "ID, background, interview and a timed subject test."], [Clock, "Shortlist in 24 hours", "Matched on subject, distance and your schedule."], [BadgeCheck, "Only pay for delivered lessons", "Payments held until each lesson is confirmed."]].map(([I, t, d]) => (
          <Card key={t as string}><IconTile icon={I as typeof Clock} /><p className="mt-4 font-display text-lg font-bold">{t as string}</p><p className="mt-1 text-sm text-ink-500">{d as string}</p></Card>
        ))}
      </div>
    </>
  );
}

export function ReferenceForm() {
  const { token } = useParams();
  const { data, isLoading, error } = useApi<{ kind: string; name: string; tutor_name: string }>(`/vetting/reference-form/${token}/`);
  const [form, setForm] = useState({ known_for: "", capacity: "", character: "", teaching_ability: "", concerns: "", would_trust_with_children: "yes" });
  const [file, setFile] = useState<File | null>(null);
  const [done, setDone] = useState(false);
  const submit = useAction(() => {
    const fd = new FormData();
    Object.entries(form).forEach(([k, v]) => fd.append(k, v));
    if (file) fd.append("id_document", file);
    return api.post(`/vetting/reference-form/${token}/`, fd);
  });
  if (isLoading) return <Loading />;
  const wrap = (children: React.ReactNode) => <div className="mx-auto max-w-2xl px-4 py-14 sm:px-6">{children}</div>;
  if (error || !data) return wrap(<Alert>This link is invalid or has already been used.</Alert>);
  if (done) return wrap(<Alert tone="green" title="Thank you">Your response has been recorded. You can close this page.</Alert>);
  const guarantor = data.kind === "guarantor";
  return (
    <>
      <Seo title={guarantor ? "Guarantor form" : "Reference form"} />
      <PageHero eyebrow={guarantor ? "Guarantor form" : "Reference request"} title={`For ${data.tutor_name}`}
        subtitle={`Hello ${data.name}. ${data.tutor_name} has applied to tutor children in their homes through TutorBridge. Your honest answers help keep children safe.`} />
      {wrap(
        <Card>
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); submit.mutate(undefined, { onSuccess: () => setDone(true) }); }}>
            <ErrorAlert error={submit.error} />
            <div className="grid gap-4 sm:grid-cols-2">
              <Input label="How long have you known them?" required value={form.known_for} onChange={(e) => setForm({ ...form, known_for: e.target.value })} />
              <Input label="In what capacity?" required value={form.capacity} onChange={(e) => setForm({ ...form, capacity: e.target.value })} />
            </div>
            <Textarea label="How would you describe their character and reliability?" required value={form.character} onChange={(e) => setForm({ ...form, character: e.target.value })} />
            {!guarantor && <Textarea label="How would you describe their teaching ability?" value={form.teaching_ability} onChange={(e) => setForm({ ...form, teaching_ability: e.target.value })} />}
            <Textarea label="Any concerns about them working with children?" value={form.concerns} onChange={(e) => setForm({ ...form, concerns: e.target.value })} />
            <Select label="Would you trust them alone with a child in your home?" value={form.would_trust_with_children} onChange={(e) => setForm({ ...form, would_trust_with_children: e.target.value })}>
              <option value="yes">Yes</option><option value="no">No</option><option value="unsure">Not sure</option>
            </Select>
            {guarantor && (
              <div>
                <label className="block text-[13px] font-semibold text-ink-700">Upload your ID (NIN slip, driver's licence or passport)</label>
                <input type="file" accept=".pdf,.jpg,.jpeg,.png" className="mt-2 block w-full text-sm file:mr-3 file:rounded-xl file:border-0 file:bg-brand-50 file:px-4 file:py-2 file:font-semibold file:text-brand-700" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
              </div>
            )}
            <p className="text-xs text-ink-500">Our team may call you to confirm your answers.</p>
            <Button type="submit" size="lg" icon={Send} loading={submit.isPending}>Submit</Button>
          </form>
        </Card>,
      )}
    </>
  );
}
