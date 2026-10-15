import {
  ArrowRight, Banknote, BookOpenCheck, CalendarCheck, Check, ClipboardList, CreditCard, Fingerprint, Gavel, Globe, GraduationCap, HeartHandshake,
  Home as HomeIcon, IdCard, KeyRound, Landmark, LineChart, MapPin, MessageSquareLock, PhoneCall, RefreshCw, Scale, Search, ShieldCheck, Siren, Sparkles,
  Star, TrendingUp, UserCheck, Users, Video, Wallet, Award, FileCheck2, ScrollText, type LucideIcon,
} from "lucide-react";
import { motion } from "motion/react";
import { lazy, Suspense, type ReactNode, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Prose } from "@/components/Layout";
import { CtaBand, Counter, Eyebrow, FaqAccordion, HeroMockup, Marquee, PageHero, SectionHeading } from "@/components/marketing";
import { Seo } from "@/components/Seo";
import { Badge, Button, ButtonLink, Card, IconTile, Reveal, type TileTone } from "@/components/ui";
import { qs } from "@/lib/api";
import { cn } from "@/lib/cn";
import { naira } from "@/lib/format";
import { useApi, useRefData } from "@/lib/hooks";

// Swiper is only used by this carousel, so it loads in its own chunk.
const FeaturedTutors = lazy(() => import("./FeaturedTutors"));

const EXAMS = ["Common Entrance", "BECE", "WAEC", "NECO", "JAMB / UTME", "IGCSE", "Checkpoint", "SAT", "A-Levels", "Phonics & early reading", "Special learning support"];

const VETTING: [string, string, LucideIcon][] = [
  ["Identity", "NIN matched to a live selfie by a licensed KYC provider.", Fingerprint],
  ["Bank account", "Account name must match the verified identity.", Landmark],
  ["Credentials", "Degree, NCE, TRCN and certificates reviewed by our team.", FileCheck2],
  ["Subject test", "Timed test for every subject and level they teach.", ClipboardList],
  ["Interview", "Video interview: teaching demo and safeguarding scenarios.", Video],
  ["References", "Two referees, at least one professional, contacted directly.", PhoneCall],
  ["Guarantor", "Signed guarantor form with ID, verified by phone.", IdCard],
  ["Address", "Residential address verified.", MapPin],
  ["Background", "Police character certificate before any home visit.", ShieldCheck],
  ["Safeguarding", "Child-safety training and a signed code of conduct.", HeartHandshake],
  ["Every 12 months", "All checks refreshed annually.", RefreshCw],
];

// --- Home ----------------------------------------------------------------------

export function Home() {
  return (
    <>
      <Seo title="TutorBridge — Safe, vetted home tutors in Lagos" description="Every tutor ID-verified, background-checked, interviewed and tested. Pay safely, track every lesson with check-in codes, and only pay for lessons delivered." />
      <Hero />
      <section className="relative -mt-px border-b border-ink-100 bg-cream py-10">
        <p className="mb-5 text-center text-xs font-semibold tracking-[0.16em] text-ink-400 uppercase">Specialists for every stage and every exam</p>
        <Marquee items={EXAMS} />
      </section>
      <Numbers />
      <Bento />
      <Steps />
      <VettingSection />
      <Suspense fallback={null}><FeaturedTutors /></Suspense>
      <Audiences />
      <HomeFaq />
      <CtaBand title={<>Your child deserves a tutor you <span className="text-gold-300">never have to worry about.</span></>} subtitle="Tell us what you need — we'll send a shortlist of vetted tutors within 24 hours."
        primary={{ to: "/signup?role=parent", label: "Request a tutor — it's free" }} secondary={{ to: "/tutors", label: "Browse tutors" }} />
    </>
  );
}

function Hero() {
  const { data: ref } = useRefData();
  const nav = useNavigate();
  const [subject, setSubject] = useState("");
  const [area, setArea] = useState("");
  return (
    <section className="grain relative overflow-hidden bg-brand-950 pt-[72px]">
      <div className="bg-grid pointer-events-none absolute inset-0 opacity-70 [mask-image:radial-gradient(ellipse_at_top,black,transparent_75%)]" />
      <div className="absolute -top-40 right-[-10%] size-[42rem] rounded-full bg-brand-500/30 blur-[120px]" />
      <div className="absolute bottom-[-30%] left-[-10%] size-[36rem] rounded-full bg-gold-400/15 blur-[120px]" />
      <div className="relative mx-auto grid max-w-7xl items-center gap-16 px-4 pt-14 pb-24 sm:px-6 lg:grid-cols-[1.1fr_1fr] lg:pt-20 lg:pb-32">
        <div>
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
            <Eyebrow light>Now matching families across Lagos</Eyebrow>
          </motion.div>
          <motion.h1 initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            className="mt-6 font-display text-[2.75rem] leading-[1.02] font-bold tracking-tight text-white sm:text-6xl lg:text-[4.4rem]">
            Home tutors you can{" "}
            <span className="relative inline-block text-gold-300">
              trust
              <svg viewBox="0 0 200 20" className="absolute -bottom-2 left-0 w-full" preserveAspectRatio="none" aria-hidden="true">
                <motion.path d="M3 14 C 50 4, 120 4, 197 12" stroke="currentColor" strokeWidth="5" fill="none" strokeLinecap="round"
                  initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ delay: 0.7, duration: 0.9, ease: "easeInOut" }} />
              </svg>
            </span>{" "}
            in your home.
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18, duration: 0.7 }}
            className="mt-7 max-w-xl text-lg leading-relaxed text-brand-100/80 sm:text-xl">
            Every tutor is identity-checked, background-checked, interviewed and tested. You pay us — not a stranger — and you only pay for lessons that actually happened.
          </motion.p>

          <motion.form initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.28, duration: 0.7 }}
            onSubmit={(e) => { e.preventDefault(); nav(`/tutors${qs({ subject, area })}`); }}
            className="mt-9 flex max-w-xl flex-col gap-2 rounded-3xl bg-white p-2 shadow-[0_20px_60px_-15px_rgb(0_0_0/0.5)] sm:flex-row sm:items-center sm:rounded-full">
            <label className="flex flex-1 items-center gap-2.5 rounded-full px-4 py-2.5">
              <GraduationCap className="size-5 shrink-0 text-brand-600" />
              <span className="sr-only">Subject</span>
              <select value={subject} onChange={(e) => setSubject(e.target.value)} className="w-full appearance-none bg-transparent text-[15px] font-medium text-ink-800 outline-none">
                <option value="">Any subject</option>
                {ref?.subjects.map((s) => <option key={s.id} value={s.slug}>{s.name}</option>)}
              </select>
            </label>
            <span className="hidden h-8 w-px bg-ink-200 sm:block" />
            <label className="flex flex-1 items-center gap-2.5 rounded-full px-4 py-2.5">
              <MapPin className="size-5 shrink-0 text-brand-600" />
              <span className="sr-only">Area</span>
              <select value={area} onChange={(e) => setArea(e.target.value)} className="w-full appearance-none bg-transparent text-[15px] font-medium text-ink-800 outline-none">
                <option value="">Anywhere in Lagos</option>
                {ref?.areas.map((a) => <option key={a.id} value={a.slug}>{a.name}</option>)}
              </select>
            </label>
            <Button type="submit" size="lg" icon={Search} className="rounded-full">Find tutors</Button>
          </motion.form>

          <motion.ul initial="hidden" animate="show" variants={{ show: { transition: { staggerChildren: 0.08, delayChildren: 0.45 } } }}
            className="mt-8 flex flex-wrap gap-x-6 gap-y-3 text-sm text-brand-100/85">
            {[["11-step vetting", ShieldCheck], ["Payment held in escrow", Wallet], ["Free tutor replacement", RefreshCw]].map(([t, I]) => {
              const Icon = I as LucideIcon;
              return (
                <motion.li key={t as string} variants={{ hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0 } }} className="flex items-center gap-2">
                  <span className="flex size-6 items-center justify-center rounded-full bg-gold-300/15 text-gold-300"><Icon className="size-3.5" /></span>{t as string}
                </motion.li>
              );
            })}
          </motion.ul>
        </div>
        <div className="relative lg:pl-6"><HeroMockup /></div>
      </div>
      {/* Curved bottom edge */}
      <svg className="absolute -bottom-px left-0 w-full text-cream" viewBox="0 0 1440 60" preserveAspectRatio="none" aria-hidden="true"><path fill="currentColor" d="M0 60V20c240 26 480 40 720 40S1200 46 1440 20v40z" /></svg>
    </section>
  );
}

function Numbers() {
  const items: [ReactNode, string, string][] = [
    [<Counter key="a" to={11} />, "checks before any tutor enters a home", "Identity, background, interview, tests, references and more"],
    [<Counter key="b" to={24} suffix="h" />, "to your personal shortlist", "Matched by our engine, reviewed by a real person"],
    [<Counter key="c" to={6} />, "digit code proves every lesson", "Tutors can't start or finish a lesson without it"],
    [<Counter key="d" to={48} suffix="h" />, "to raise any problem", "Payment for that lesson is frozen until it's resolved"],
  ];
  return (
    <section className="mx-auto max-w-7xl px-4 py-20 sm:px-6">
      <div className="grid gap-px overflow-hidden rounded-[2rem] bg-ink-100 shadow-soft sm:grid-cols-2 lg:grid-cols-4">
        {items.map(([num, label, sub], i) => (
          <Reveal key={i} delay={i * 0.08} className="bg-white p-8">
            <p className="font-display text-5xl font-bold tracking-tight text-brand-700">{num}</p>
            <p className="mt-3 font-semibold text-ink-900">{label}</p>
            <p className="mt-1 text-sm text-ink-500">{sub}</p>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

function Bento() {
  return (
    <section className="mx-auto max-w-7xl px-4 pb-24 sm:px-6">
      <SectionHeading eyebrow="Why families choose TutorBridge" title={<>Peace of mind is <span className="text-brand-600">built in</span>, not bolted on.</>}
        subtitle="Parents already find tutors through word of mouth. What they can't get is certainty — about who's in their home, and whether lessons are really happening." />
      <div className="mt-14 grid gap-5 md:grid-cols-6">
        <Reveal className="md:col-span-4">
          <div className="group relative h-full overflow-hidden rounded-[2rem] bg-brand-950 p-8 text-white sm:p-10">
            <div className="bg-grid pointer-events-none absolute inset-0 opacity-50" />
            <div className="absolute -right-20 -bottom-20 size-72 rounded-full bg-brand-500/30 blur-3xl transition-transform duration-700 group-hover:scale-125" />
            <div className="relative grid gap-8 sm:grid-cols-[1fr_auto]">
              <div>
                <IconTile icon={ShieldCheck} tone="dark" size="lg" />
                <h3 className="mt-6 font-display text-2xl font-bold sm:text-3xl">Obsessively vetted tutors</h3>
                <p className="mt-3 max-w-md leading-relaxed text-brand-100/75">Every tutor passes an 11-stage check before they can be booked — and it's refreshed every year.</p>
                <ButtonLink to="/safety" variant="accent" className="mt-7" iconRight={ArrowRight}>See the full process</ButtonLink>
              </div>
              <ul className="grid grid-cols-2 gap-2 self-center text-sm sm:grid-cols-1">
                {VETTING.slice(0, 6).map(([t, , I], i) => (
                  <motion.li key={t} initial={{ opacity: 0, x: 12 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: 0.2 + i * 0.07 }}
                    className="flex items-center gap-2 rounded-xl bg-white/5 px-3 py-2 ring-1 ring-white/10">
                    <I className="size-4 text-gold-300" /> {t} <Check className="ml-auto size-4 text-brand-300" />
                  </motion.li>
                ))}
              </ul>
            </div>
          </div>
        </Reveal>
        <BentoCard className="md:col-span-2" icon={KeyRound} tone="gold" title="Lesson check-in codes" delay={0.1}
          body="A 6-digit code only you can see. The tutor enters it on arrival and departure — every lesson timestamped." />
        <BentoCard className="md:col-span-2" icon={Wallet} tone="green" title="Pay safely, pay once" delay={0.05}
          body="Your money is held in escrow and released only after each lesson is confirmed. Card, transfer or USSD." />
        <BentoCard className="md:col-span-2" icon={LineChart} tone="blue" title="Progress you can see" delay={0.1}
          body="A lesson note after every class and a monthly progress report you can download." />
        <BentoCard className="md:col-span-2" icon={RefreshCw} tone="violet" title="Free replacement" delay={0.15}
          body="Not the right fit? We'll find another tutor at no cost — your remaining balance moves with you." />
        <BentoCard className="md:col-span-3" icon={Globe} tone="gold" title="Paying from abroad?" delay={0.05}
          body="Diaspora parents and relatives can pay by card in naira and follow every lesson — attendance, notes and reports — from anywhere." />
        <BentoCard className="md:col-span-3" icon={Siren} tone="red" title="A safety team on call" delay={0.1}
          body="One tap on any lesson alerts our on-call safety officer by SMS and email. Every report is investigated within 24 hours." />
      </div>
    </section>
  );
}

function BentoCard({ icon, tone, title, body, className, delay = 0 }: { icon: LucideIcon; tone: TileTone; title: string; body: string; className?: string; delay?: number }) {
  return (
    <Reveal delay={delay} className={className}>
      <motion.div whileHover={{ y: -4 }} transition={{ type: "spring", stiffness: 300, damping: 22 }}
        className="h-full rounded-[2rem] border border-ink-100 bg-white p-7 shadow-soft transition-shadow hover:shadow-lift">
        <IconTile icon={icon} tone={tone} size="lg" />
        <h3 className="mt-5 font-display text-xl font-bold text-ink-950">{title}</h3>
        <p className="mt-2 leading-relaxed text-ink-500">{body}</p>
      </motion.div>
    </Reveal>
  );
}

const STEPS: [string, string, LucideIcon][] = [
  ["Tell us what you need", "Your child's class, subjects, goals, days and budget. Takes three minutes.", ClipboardList],
  ["Get your shortlist", "Three vetted tutors within 24 hours — matched on subject, distance, schedule and fit.", Users],
  ["Book a trial", "Pay securely. Your money is held in escrow until each lesson is confirmed.", CreditCard],
  ["Track every lesson", "Check-in codes, lesson notes and a monthly progress report.", CalendarCheck],
];

function Steps() {
  return (
    <section className="relative overflow-hidden border-y border-ink-100 bg-sand/60 py-24">
      <div className="bg-grid-dark pointer-events-none absolute inset-0 opacity-60" />
      <div className="relative mx-auto max-w-7xl px-4 sm:px-6">
        <SectionHeading eyebrow="How it works" title="From request to first lesson in four steps" />
        <div className="relative mt-16 grid gap-6 md:grid-cols-4">
          <div className="absolute top-8 right-[12%] left-[12%] hidden h-0.5 md:block">
            <motion.div initial={{ scaleX: 0 }} whileInView={{ scaleX: 1 }} viewport={{ once: true }} transition={{ duration: 1.4, ease: "easeInOut" }}
              className="h-full origin-left bg-[repeating-linear-gradient(90deg,var(--color-brand-300)_0_8px,transparent_8px_16px)]" />
          </div>
          {STEPS.map(([t, d, Icon], i) => (
            <Reveal key={t} delay={i * 0.15} className="relative text-center">
              <div className="relative mx-auto flex size-16 items-center justify-center rounded-2xl bg-white shadow-lift ring-1 ring-ink-100">
                <Icon className="size-7 text-brand-600" />
                <span className="absolute -top-2 -right-2 flex size-6 items-center justify-center rounded-full bg-gold-300 font-display text-xs font-bold text-ink-950">{i + 1}</span>
              </div>
              <h3 className="mt-6 font-display text-lg font-bold text-ink-950">{t}</h3>
              <p className="mx-auto mt-2 max-w-60 text-[15px] leading-relaxed text-ink-500">{d}</p>
            </Reveal>
          ))}
        </div>
        <div className="mt-14 text-center"><ButtonLink to="/how-it-works" variant="secondary" iconRight={ArrowRight}>The full picture</ButtonLink></div>
      </div>
    </section>
  );
}

function VettingSection() {
  return (
    <section className="grain relative overflow-hidden bg-brand-950 py-24 text-white">
      <div className="bg-grid pointer-events-none absolute inset-0 opacity-50" />
      <div className="absolute top-0 left-1/3 size-[36rem] rounded-full bg-brand-600/20 blur-[120px]" />
      <div className="relative mx-auto grid max-w-7xl gap-14 px-4 sm:px-6 lg:grid-cols-[1fr_1.15fr]">
        <div className="lg:sticky lg:top-28 lg:self-start">
          <SectionHeading light align="left" eyebrow="Trust & safety" title={<>Safety isn't a feature. <span className="text-gold-300">It's the product.</span></>}
            subtitle="Tutors visit private homes and work with children. That's why every one of these checks is mandatory — not optional, not 'premium'." />
          <div className="mt-8 grid grid-cols-2 gap-3 text-sm">
            {[["Lessons in a common area", HomeIcon], ["An adult always at home", UserCheck], ["No private contact", MessageSquareLock], ["Zero-tolerance policy", Scale]].map(([t, I]) => {
              const Icon = I as LucideIcon;
              return <div key={t as string} className="flex items-center gap-2.5 rounded-2xl bg-white/5 p-3.5 ring-1 ring-white/10"><Icon className="size-4.5 shrink-0 text-gold-300" />{t as string}</div>;
            })}
          </div>
        </div>
        <ol className="relative space-y-3">
          <div className="absolute top-4 bottom-4 left-[27px] w-px bg-gradient-to-b from-gold-300/60 via-brand-400/40 to-transparent" />
          {VETTING.map(([t, d, Icon], i) => (
            <motion.li key={t} initial={{ opacity: 0, x: 24 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true, margin: "-40px" }} transition={{ delay: i * 0.04, duration: 0.5 }}
              className="group relative flex gap-4 rounded-2xl p-3 transition hover:bg-white/5">
              <span className="relative z-10 flex size-[54px] shrink-0 items-center justify-center rounded-2xl bg-brand-900 ring-1 ring-white/15 transition group-hover:bg-brand-700">
                <Icon className="size-5 text-gold-300" />
              </span>
              <div className="pt-1.5">
                <p className="font-display text-lg font-semibold"><span className="mr-2 text-sm text-brand-300">{String(i + 1).padStart(2, "0")}</span>{t}</p>
                <p className="mt-0.5 text-[15px] text-brand-100/70">{d}</p>
              </div>
            </motion.li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function Audiences() {
  return (
    <section className="mx-auto grid max-w-7xl gap-6 px-4 pb-24 sm:px-6 lg:grid-cols-2">
      <Reveal>
        <div className="relative h-full overflow-hidden rounded-[2rem] bg-gradient-to-br from-gold-100 via-gold-50 to-white p-9 ring-1 ring-gold-200 sm:p-11">
          <div className="absolute -top-10 -right-10 size-48 rounded-full bg-gold-300/30 blur-2xl" />
          <Badge tone="amber">For parents</Badge>
          <h3 className="mt-5 font-display text-3xl font-bold text-ink-950">Stop gambling on tutors.</h3>
          <ul className="mt-6 space-y-3.5 text-ink-700">
            {["Free replacement if the fit isn't right", "Unused package balance stays in your wallet", "Pay from abroad by card, in naira", "Dispute any lesson within 48 hours"].map((t) => (
              <li key={t} className="flex items-start gap-3"><span className="mt-0.5 flex size-5 items-center justify-center rounded-full bg-brand-600 text-white"><Check className="size-3" strokeWidth={3} /></span>{t}</li>
            ))}
          </ul>
          <ButtonLink to="/signup?role=parent" size="lg" className="mt-9" iconRight={ArrowRight}>Request a tutor</ButtonLink>
        </div>
      </Reveal>
      <Reveal delay={0.1}>
        <div className="grain relative h-full overflow-hidden rounded-[2rem] bg-ink-950 p-9 text-white sm:p-11">
          <div className="bg-grid pointer-events-none absolute inset-0 opacity-40" />
          <div className="absolute -bottom-16 -left-10 size-56 rounded-full bg-brand-500/30 blur-3xl" />
          <div className="relative">
            <Badge tone="green" className="bg-white/10 text-brand-200 ring-white/15">For teachers</Badge>
            <h3 className="mt-5 font-display text-3xl font-bold">Teach more. Chase money never.</h3>
            <ul className="mt-6 space-y-3.5 text-white/80">
              {[["Paying families near your route", MapPin], ["Paid every week, guaranteed once confirmed", Banknote], ["A verified profile and ratings that grow", Award], ["Commission falls as you reach Gold & Elite", TrendingUp]].map(([t, I]) => {
                const Icon = I as LucideIcon;
                return <li key={t as string} className="flex items-start gap-3"><Icon className="mt-0.5 size-5 shrink-0 text-gold-300" />{t as string}</li>;
              })}
            </ul>
            <ButtonLink to="/teach" variant="accent" size="lg" className="mt-9" iconRight={ArrowRight}>Teach with TutorBridge</ButtonLink>
          </div>
        </div>
      </Reveal>
    </section>
  );
}

const FALLBACK_FAQ = [
  { q: "How do you vet tutors?", a: "Every tutor passes an 11-stage check: NIN and selfie verification, bank name match, credential review, a timed subject test, a video interview, two references, a guarantor, address verification, a police character certificate and safeguarding training." },
  { q: "When is the tutor paid?", a: "Your payment is held by TutorBridge and released to the tutor only after each lesson is confirmed — by you, or automatically 48 hours after it ends if you haven't raised a problem." },
  { q: "What if I need to cancel?", a: "Cancel at least 24 hours before and the full lesson fee goes back to your wallet. With less notice, 50% is paid to the tutor for their time." },
];

function HomeFaq() {
  const { data } = useApi<{ question: string; answer: string; audience: string }[]>("/faqs/?audience=parent");
  const items = data?.length ? data.slice(0, 6).map((f) => ({ q: f.question, a: f.answer })) : FALLBACK_FAQ;
  return (
    <section className="mx-auto grid max-w-7xl gap-12 px-4 pb-24 sm:px-6 lg:grid-cols-[1fr_1.4fr]">
      <div>
        <SectionHeading align="left" eyebrow="Questions" title="Everything parents ask us" subtitle="Can't find your answer? Our team replies within one working day." />
        <ButtonLink to="/faq" variant="secondary" className="mt-8" iconRight={ArrowRight}>All FAQs</ButtonLink>
      </div>
      <Reveal><FaqAccordion items={items} /></Reveal>
    </section>
  );
}

// --- How it works -------------------------------------------------------------

export function HowItWorks() {
  const { data } = useRefData();
  const c = data?.config;
  const [who, setWho] = useState<"parent" | "tutor">("parent");
  const parent: [string, string, LucideIcon][] = [
    ["Create your free account", "Verify your phone and add your child — first name, class and learning needs only.", UserCheck],
    ["Submit a lesson request", "Subjects, goals, days, times and budget — or browse tutors and request one directly.", ClipboardList],
    ["Receive your shortlist", "Within 24 hours: vetted tutors with verified badges, ratings and rates. Contact details are never shared.", Users],
    ["Book and pay securely", "Book a trial or a package by card, bank transfer or USSD. Your payment is held in escrow.", Wallet],
    ["The tutor confirms", `Within ${c?.booking_accept_hours ?? 12} hours — or we automatically offer your booking to the next tutor on your shortlist.`, CalendarCheck],
    ["Lesson day", "Give the tutor your check-in code on arrival and check-out code at the end. You'll get a lesson note.", KeyRound],
    ["Confirm & review", `Confirm the lesson, or it's confirmed automatically ${c?.dispute_window_hours ?? 48} hours later if you haven't raised a problem.`, Star],
  ];
  const tutor: [string, string, LucideIcon][] = [
    ["Apply in minutes", "Create an account and build your profile: subjects, levels, areas, availability and rate.", UserCheck],
    ["Complete vetting", "ID, bank, documents, subject tests, interview, references, guarantor and safeguarding training.", ShieldCheck],
    ["Go live", "Once approved and your background check is in, families can find you.", Sparkles],
    ["Accept bookings", "Respond within 12 hours. Payment is already secured before you're even asked.", CalendarCheck],
    ["Teach & log the lesson", "Check in and out with the family's codes and write a short lesson note.", BookOpenCheck],
    ["Get paid weekly", "Confirmed lessons become cleared earnings, sent to your bank account every week.", Banknote],
  ];
  const steps = who === "parent" ? parent : tutor;
  return (
    <>
      <Seo title="How it works" description="From lesson request to first lesson: vetted shortlist in 24 hours, escrow payments and check-in codes for every lesson." />
      <PageHero eyebrow="How it works" title="Simple for you. Rigorous behind the scenes." subtitle="We stay in the loop at every step — verification before contact, escrow before the lesson, check-in during it, and payment after it." />
      <section className="mx-auto max-w-4xl px-4 py-16 sm:px-6">
        <div className="flex justify-center">
          <div role="tablist" className="inline-flex rounded-2xl bg-ink-100/70 p-1">
            {(["parent", "tutor"] as const).map((w) => (
              <button key={w} role="tab" aria-selected={who === w} onClick={() => setWho(w)} className={cn("relative min-h-11 rounded-xl px-6 text-sm font-semibold", who === w ? "text-ink-950" : "text-ink-500")}>
                {who === w && <motion.span layoutId="hiw-tab" className="absolute inset-0 rounded-xl bg-white shadow-soft" />}
                <span className="relative">{w === "parent" ? "For parents" : "For tutors"}</span>
              </button>
            ))}
          </div>
        </div>
        <ol className="relative mt-14 space-y-4">
          <div className="absolute top-6 bottom-6 left-7 w-px bg-gradient-to-b from-brand-300 to-transparent" />
          {steps.map(([t, d, Icon], i) => (
            <motion.li key={who + t} initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.06 }}
              className="relative flex gap-5 rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-100">
              <span className="relative z-10 flex size-14 shrink-0 items-center justify-center rounded-2xl bg-brand-600 text-white shadow-glow"><Icon className="size-6" /></span>
              <div className="pt-1">
                <p className="text-xs font-semibold tracking-wider text-brand-600 uppercase">Step {i + 1}</p>
                <h3 className="font-display text-lg font-bold text-ink-950">{t}</h3>
                <p className="mt-1 leading-relaxed text-ink-500">{d}</p>
              </div>
            </motion.li>
          ))}
        </ol>
      </section>
      <CtaBand title="Ready when you are." subtitle="It's free to create an account and submit a request." primary={who === "parent" ? { to: "/signup?role=parent", label: "Request a tutor" } : { to: "/signup?role=tutor", label: "Apply to teach" }} />
    </>
  );
}

// --- Safety -------------------------------------------------------------------

export function Safety() {
  const during: [string, string, LucideIcon, TileTone][] = [
    ["Check-in & check-out codes", "A 6-digit code, visible only to you, is entered by the tutor on arrival and departure — timestamping every lesson.", KeyRound, "gold"],
    ["Location stamp", "With the tutor's consent, check-in records an approximate location to confirm they were at your address.", MapPin, "blue"],
    ["One-tap safety button", "From any lesson page. Our on-call safety officer is alerted immediately by SMS and email.", Siren, "red"],
    ["Code of conduct", "Common area of the home, an adult present, no private contact with the child, no photos of the child.", ScrollText, "green"],
    ["Masked messaging", "Phone numbers, emails and social handles are hidden in messages, and all conversations are kept for disputes.", MessageSquareLock, "violet"],
    ["Fair disputes", "Raise a problem within 48 hours; payment for that lesson is frozen until our team resolves it.", Gavel, "ink"],
  ];
  return (
    <>
      <Seo title="Safety standards" description="The 11-step vetting pipeline every TutorBridge tutor passes, and the safeguards in place during every lesson." />
      <PageHero dark eyebrow="Trust & safety" title={<>Who enters your home <span className="text-gold-300">matters.</span></>}
        subtitle="Tutors visit private homes and work with children. These controls are mandatory for every tutor and every lesson." />
      <section className="mx-auto max-w-7xl px-4 py-20 sm:px-6">
        <SectionHeading eyebrow="Before the first lesson" title="The 11-step vetting pipeline" />
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {VETTING.map(([t, d, Icon], i) => (
            <Reveal key={t} delay={(i % 3) * 0.06}>
              <div className="flex h-full gap-4 rounded-3xl border border-ink-100 bg-white p-5 shadow-soft">
                <IconTile icon={Icon} />
                <div>
                  <p className="font-display font-bold text-ink-950"><span className="mr-1.5 text-brand-500">{String(i + 1).padStart(2, "0")}</span>{t}</p>
                  <p className="mt-1 text-sm leading-relaxed text-ink-500">{d}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>
      <section className="border-y border-ink-100 bg-sand/60 py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <SectionHeading eyebrow="During every lesson" title="Safeguards that work while you're at work" />
          <div className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {during.map(([t, d, Icon, tone], i) => (
              <BentoCard key={t} icon={Icon} tone={tone} title={t} body={d} delay={(i % 3) * 0.06} />
            ))}
          </div>
        </div>
      </section>
      <section className="mx-auto max-w-4xl px-4 py-16 sm:px-6">
        <div className="flex flex-col items-center gap-5 rounded-[2rem] bg-red-50 p-8 text-center ring-1 ring-red-200 sm:flex-row sm:text-left">
          <IconTile icon={Siren} tone="red" size="lg" />
          <div>
            <p className="font-display text-xl font-bold text-red-900">In an emergency, call 112 first.</p>
            <p className="mt-1 text-red-800">Then use the safety button on the lesson page so our team can act immediately. Any serious complaint suspends the tutor pending investigation.</p>
          </div>
        </div>
      </section>
    </>
  );
}

// --- Pricing ------------------------------------------------------------------

export function Pricing() {
  const { data } = useRefData();
  const c = data?.config;
  return (
    <>
      <Seo title="Pricing" description="Transparent hourly rates by level. You see the full price before you pay — no hidden fees." />
      <PageHero eyebrow="Pricing" title="Transparent pricing. No surprises." subtitle="Each tutor sets an hourly rate within our bands for the level they teach. You see the full price before you pay." />
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data?.levels.map((l, i) => (
            <Reveal key={l.id} delay={(i % 3) * 0.06}>
              <motion.div whileHover={{ y: -4 }} className={cn("relative h-full overflow-hidden rounded-[2rem] p-7 shadow-soft ring-1", i === 3 ? "bg-brand-950 text-white ring-brand-800" : "bg-white ring-ink-100")}>
                {i === 3 && <Badge tone="amber" className="absolute top-5 right-5">Exam years</Badge>}
                <p className={cn("text-sm font-semibold tracking-wide uppercase", i === 3 ? "text-gold-300" : "text-brand-600")}>{l.name}</p>
                <p className="mt-4 font-display text-4xl font-bold">{naira(l.min_rate_kobo)}<span className={cn("text-2xl", i === 3 ? "text-white/50" : "text-ink-300")}> – </span>{naira(l.max_rate_kobo)}</p>
                <p className={cn("mt-1 text-sm", i === 3 ? "text-white/60" : "text-ink-500")}>per hour, set by the tutor</p>
              </motion.div>
            </Reveal>
          ))}
        </div>

        <div className="mt-12 grid gap-6 lg:grid-cols-2">
          <Card title="Worked example" subtitle="One child, one month" icon={Banknote}>
            <dl className="divide-y divide-ink-100 text-[15px]">
              {[["12 lessons × 1.5 h × ₦6,000/h", "₦108,000"], ["Matching fee on your first trial", `${naira(c?.matching_fee_kobo ?? 500000)} · credited back on your package`], ["Gateway fees", "Absorbed by TutorBridge"]].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4 py-3"><dt className="text-ink-600">{k}</dt><dd className="text-right font-semibold text-ink-900">{v}</dd></div>
              ))}
              <div className="flex justify-between gap-4 pt-4"><dt className="font-display text-lg font-bold">You pay</dt><dd className="font-display text-lg font-bold text-brand-700">₦108,000</dd></div>
            </dl>
          </Card>
          <Card title="Cancellations & refunds" subtitle="Fair to families and tutors" icon={Scale}>
            <ul className="space-y-3.5 text-[15px] text-ink-700">
              {[
                `Cancel with ${c?.late_cancel_notice_hours ?? 24}+ hours' notice — full credit to your wallet.`,
                `Less notice — ${c?.late_cancel_tutor_pct ?? 50}% goes to the tutor for their time.`,
                "Tutor doesn't show up — full credit, and the tutor gets a strike.",
                "Unused balance stays in your wallet; cash refunds on request (minus gateway costs).",
              ].map((t) => <li key={t} className="flex gap-3"><Check className="mt-0.5 size-5 shrink-0 text-brand-600" />{t}</li>)}
            </ul>
          </Card>
        </div>
      </section>
      <CtaBand title="See real tutors and real rates." subtitle="Browse vetted tutors in your area — no account needed." primary={{ to: "/tutors", label: "Browse tutors" }} secondary={{ to: "/signup?role=parent", label: "Request a tutor" }} />
    </>
  );
}

// --- Teach with us ------------------------------------------------------------

export function TeachWithUs() {
  return (
    <>
      <Seo title="Teach with TutorBridge" description="Paying families near your route, weekly pay, and a verified reputation that grows with you." />
      <PageHero dark eyebrow="For teachers" title={<>Do what you love. <span className="text-gold-300">We'll handle the rest.</span></>}
        subtitle="We bring you paying families, handle the money and the awkward conversations, and pay you on time — every week.">
        <ButtonLink to="/signup?role=tutor" variant="accent" size="lg" iconRight={ArrowRight}>Apply in 10 minutes</ButtonLink>
      </PageHero>
      <section className="mx-auto max-w-7xl px-4 py-20 sm:px-6">
        <div className="grid gap-5 md:grid-cols-3">
          <BentoCard icon={MapPin} tone="green" title="Families near your route" body="Matched to your subjects, levels, availability and the areas you choose to serve." />
          <BentoCard icon={Banknote} tone="gold" title="Guaranteed weekly pay" body="Families pay upfront. Once a lesson is confirmed, it's paid — straight to your bank every week." delay={0.06} />
          <BentoCard icon={TrendingUp} tone="blue" title="Earn more as you grow" body="Commission starts at 20% and falls as you reach Gold and Elite through hours, ratings and reliability." delay={0.12} />
        </div>
        <div className="mt-16 grid items-start gap-10 lg:grid-cols-2">
          <SectionHeading align="left" eyebrow="What you'll need" title="Have these ready before you start" subtitle="Your progress saves as you go, so you can finish your application over a few days." />
          <Card>
            <ul className="grid gap-3 text-[15px] text-ink-700 sm:grid-cols-2">
              {[["Your NIN and a phone camera", Fingerprint], ["A bank account in your name", Landmark], ["CV and degree or NCE certificate", FileCheck2], ["Two referees and a guarantor", Users], ["Proof of address", HomeIcon], ["Police character certificate", ShieldCheck]].map(([t, I]) => {
                const Icon = I as LucideIcon;
                return <li key={t as string} className="flex items-start gap-3 rounded-2xl bg-ink-50/70 p-3.5"><Icon className="mt-0.5 size-5 shrink-0 text-brand-600" />{t as string}</li>;
              })}
            </ul>
          </Card>
        </div>
      </section>
      <CtaBand title="Build your tutoring career on trust." subtitle="Starting your application takes about 10 minutes, and your progress saves as you go." primary={{ to: "/signup?role=tutor", label: "Start your application" }} secondary={{ to: "/faq", label: "Tutor FAQs" }} />
    </>
  );
}

// --- Legal --------------------------------------------------------------------

const LEGAL: Record<string, { title: string; body: string[] }> = {
  terms: {
    title: "Terms of Service",
    body: [
      "These terms are a working draft and must be reviewed by a Nigerian lawyer before launch.",
      "TutorBridge connects parents and guardians with independent tutors. Payments for lessons are made to TutorBridge and held until lessons are confirmed. Protections — including the lesson guarantee, free replacement, dispute resolution and safety support — apply only to bookings paid through TutorBridge.",
      "Parents and tutors agree not to arrange lessons privately with people they met through TutorBridge for 12 months after their last booking, unless the agreed buy-out fee is paid.",
    ],
  },
  privacy: {
    title: "Privacy Policy",
    body: [
      "This policy is a working draft prepared for compliance with the Nigeria Data Protection Act 2023 and must be reviewed before launch.",
      "We collect only what we need: for children, a first name, class and learning needs, with a parent's consent. Sensitive data (identity results, bank details, learning notes) is encrypted at rest.",
      "You can download your data, correct it or ask us to delete your account from your account page. Financial records are kept for as long as tax law requires. Location is captured at lesson check-in only with the tutor's consent.",
    ],
  },
  refunds: {
    title: "Refund & Cancellation Policy",
    body: [
      "Cancel with at least 24 hours' notice for full credit. With less notice, 50% of the lesson fee is paid to the tutor.",
      "If a tutor doesn't show up, the lesson is credited back to you in full. You can dispute any lesson within 48 hours; payment for that lesson is frozen until we resolve it.",
      "If a trial isn't a good fit we'll find a replacement free, or refund the trial minus the matching fee. Unused balance stays as wallet credit; cash refunds are available on request minus gateway costs.",
    ],
  },
};

export function Legal() {
  const { page = "terms" } = useParams();
  const doc = LEGAL[page] ?? LEGAL.terms;
  return (
    <>
      <Seo title={doc.title} />
      <PageHero eyebrow="Legal" title={doc.title} />
      <div className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
        <Card><Prose>{doc.body.map((p, i) => <p key={i}>{p}</p>)}</Prose></Card>
      </div>
    </>
  );
}
