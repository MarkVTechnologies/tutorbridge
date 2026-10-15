import { ArrowRight, BadgeCheck, BookOpen, Clock, GraduationCap, Lock, MapPin, Quote, SlidersHorizontal, Sparkles, Target, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { PageHero } from "@/components/marketing";
import { Seo } from "@/components/Seo";
import { TutorCard } from "@/components/shared";
import { Avatar, Badge, Button, ButtonLink, Card, EmptyState, Loading, Pagination, Select, Skeleton, Stars, TierBadge } from "@/components/ui";
import { qs, type Paginated } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateOnly, naira } from "@/lib/format";
import { useApi, useRefData } from "@/lib/hooks";
import type { TutorPublic } from "@/lib/types";

const FILTER_KEYS = ["subject", "level", "area", "gender", "max_rate", "min_rating", "sort"] as const;

export function FindTutors() {
  const [params, setParams] = useSearchParams();
  const { data: ref } = useRefData();
  const [showFilters, setShowFilters] = useState(false);
  const filters = Object.fromEntries([...FILTER_KEYS, "page"].map((k) => [k, params.get(k) ?? ""]));
  const { data, isLoading } = useApi<Paginated<TutorPublic>>(`/tutors/${qs(filters)}`);
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v); else next.delete(k);
    if (k !== "page") next.delete("page");
    setParams(next);
  };
  const active = FILTER_KEYS.filter((k) => k !== "sort" && filters[k]);
  const label = (k: string, v: string) =>
    k === "subject" ? ref?.subjects.find((s) => s.slug === v)?.name : k === "level" ? ref?.levels.find((l) => l.code === v)?.name : k === "area" ? ref?.areas.find((a) => a.slug === v)?.name
      : k === "max_rate" ? `≤ ${naira(Number(v))}/hr` : k === "gender" ? `${v[0].toUpperCase()}${v.slice(1)} tutors` : v;
  const filterPanel = (
    <div className="space-y-5">
      <Select label="Subject" value={filters.subject} onChange={(e) => set("subject", e.target.value)}>
        <option value="">Any subject</option>{ref?.subjects.map((s) => <option key={s.id} value={s.slug}>{s.name}</option>)}
      </Select>
      <Select label="Level" value={filters.level} onChange={(e) => set("level", e.target.value)}>
        <option value="">Any level</option>{ref?.levels.map((l) => <option key={l.id} value={l.code}>{l.name}</option>)}
      </Select>
      <Select label="Area" value={filters.area} onChange={(e) => set("area", e.target.value)}>
        <option value="">Anywhere in Lagos</option>{ref?.areas.map((a) => <option key={a.id} value={a.slug}>{a.name}</option>)}
      </Select>
      <Select label="Tutor gender" value={filters.gender} onChange={(e) => set("gender", e.target.value)}>
        <option value="">No preference</option><option value="female">Female</option><option value="male">Male</option>
      </Select>
      <Select label="Max rate per hour" value={filters.max_rate} onChange={(e) => set("max_rate", e.target.value)}>
        <option value="">Any budget</option>{[5000, 7500, 10000, 15000, 20000].map((n) => <option key={n} value={n * 100}>Up to {naira(n * 100)}</option>)}
      </Select>
    </div>
  );
  return (
    <>
      <Seo title="Find a vetted home tutor in Lagos" description="Browse ID-verified, background-checked, interviewed and tested home tutors by subject, level and area." />
      <PageHero eyebrow="Find a tutor" title="Every tutor here passed 11 checks." subtitle="Browse by subject, level and area. Contact details stay private — booking, payment and messages all happen safely on TutorBridge." />
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6">
        <div className="grid gap-8 lg:grid-cols-[17rem_1fr]">
          <aside className="hidden lg:block">
            <div className="sticky top-24 rounded-3xl border border-ink-100 bg-white p-5 shadow-soft">
              <p className="mb-4 flex items-center gap-2 font-display font-semibold"><SlidersHorizontal className="size-4 text-brand-600" />Filters</p>
              {filterPanel}
            </div>
          </aside>
          <div>
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <p className="text-ink-600">{data ? <><strong className="text-ink-950">{data.count}</strong> vetted tutor{data.count === 1 ? "" : "s"}</> : "Searching…"}</p>
              <div className="flex items-center gap-2">
                <Button variant="secondary" size="sm" icon={SlidersHorizontal} className="lg:hidden" onClick={() => setShowFilters(true)}>Filters{active.length ? ` (${active.length})` : ""}</Button>
                <select aria-label="Sort by" className="input w-auto py-2 text-sm" value={filters.sort} onChange={(e) => set("sort", e.target.value)}>
                  <option value="">Top rated</option><option value="rate">Lowest rate</option><option value="experience">Most experienced</option>
                </select>
              </div>
            </div>
            {active.length > 0 && (
              <div className="mb-5 flex flex-wrap gap-2">
                {active.map((k) => (
                  <button key={k} onClick={() => set(k, "")} className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1.5 text-sm font-medium text-brand-800 ring-1 ring-brand-200 transition hover:bg-brand-100">
                    {label(k, filters[k])}<X className="size-3.5" />
                  </button>
                ))}
                <button onClick={() => setParams(new URLSearchParams())} className="px-2 text-sm font-medium text-ink-500 hover:text-ink-800">Clear all</button>
              </div>
            )}
            <div className="space-y-4">
              {isLoading && [0, 1, 2].map((i) => <Skeleton key={i} className="h-48 rounded-3xl" />)}
              {data?.results.length === 0 && (
                <EmptyState icon={GraduationCap} title="No tutors match these filters yet" action={<ButtonLink to="/signup?role=parent" iconRight={ArrowRight}>Send us a request instead</ButtonLink>}>
                  We're adding vetted tutors every week. Submit a request and our matching team will search for you.
                </EmptyState>
              )}
              <AnimatePresence mode="popLayout">
                {data?.results.map((t, i) => (
                  <motion.div key={t.id} layout initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ delay: i * 0.04 }}>
                    <TutorCard tutor={t} action={<RequestTutorButton tutorId={t.id} />} />
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
            {data && <Pagination page={Number(filters.page || 1)} count={data.count} onPage={(p) => set("page", String(p))} />}
          </div>
        </div>
      </div>
      <AnimatePresence>
        {showFilters && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 bg-ink-950/50" onClick={() => setShowFilters(false)} />
            <motion.div initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }} transition={{ type: "spring", stiffness: 380, damping: 38 }}
              className="absolute inset-x-0 bottom-0 max-h-[85vh] overflow-y-auto rounded-t-[2rem] bg-white p-6">
              <div className="mx-auto mb-4 h-1.5 w-12 rounded-full bg-ink-200" />
              <div className="mb-5 flex items-center justify-between"><p className="font-display text-lg font-bold">Filters</p><button onClick={() => setShowFilters(false)} aria-label="Close"><X className="size-5" /></button></div>
              {filterPanel}
              <Button className="mt-6 w-full" size="lg" onClick={() => setShowFilters(false)}>Show {data?.count ?? ""} tutors</Button>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}

function RequestTutorButton({ tutorId, size = "md" }: { tutorId: number; size?: "md" | "lg" }) {
  const { me } = useAuth();
  const nav = useNavigate();
  const target = `/parent/requests/new?tutor=${tutorId}`;
  return (
    <Button size={size} iconRight={ArrowRight} onClick={() => nav(me?.role === "parent" ? target : `/signup?role=parent&next=${encodeURIComponent(target)}`)}>
      Request this tutor
    </Button>
  );
}

export function TutorProfile() {
  const { id } = useParams();
  const { data: t, isLoading } = useApi<TutorPublic>(`/tutors/${id}/`);
  if (isLoading) return <Loading />;
  if (!t) return <div className="p-10"><EmptyState title="Tutor not found" /></div>;
  const bySubject = t.subjects.reduce<Record<string, string[]>>((acc, s) => ({ ...acc, [s.subject_name]: [...(acc[s.subject_name] ?? []), s.level_name] }), {});
  return (
    <>
      <Seo title={`${t.name} — ${t.headline}`} description={t.bio.slice(0, 155)} />
      <section className="relative overflow-hidden bg-gradient-to-b from-sand to-cream">
        <div className="bg-grid-dark pointer-events-none absolute inset-0 opacity-70 [mask-image:linear-gradient(to_bottom,black,transparent)]" />
        <div className="relative mx-auto max-w-6xl px-4 py-12 sm:px-6">
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col gap-8 rounded-[2rem] border border-ink-100 bg-white p-7 shadow-lift sm:p-9 md:flex-row md:items-center">
            <div className="relative self-start">
              <Avatar name={t.name} src={t.photo_url} size={132} />
              <BadgeCheck className="absolute right-1 bottom-1 size-9 fill-brand-500 text-white" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="font-display text-4xl font-bold text-ink-950">{t.name}</h1>
                <TierBadge tier={t.tier} />
              </div>
              <p className="mt-1 text-lg text-ink-600">{t.headline}</p>
              <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm text-ink-600">
                {t.rating_count > 0 ? <span className="flex items-center gap-1.5"><Stars value={Number(t.rating_avg)} /><strong className="text-ink-900">{Number(t.rating_avg).toFixed(1)}</strong> · {t.rating_count} reviews</span>
                  : <span className="flex items-center gap-1.5 font-medium text-gold-600"><Sparkles className="size-4" /> New on TutorBridge</span>}
                <span className="flex items-center gap-1.5"><Clock className="size-4 text-ink-400" />{Math.round(Number(t.hours_taught))} hours taught</span>
                <span className="flex items-center gap-1.5"><Target className="size-4 text-ink-400" />{t.reliability_score}% reliability</span>
                {t.home_area_name && <span className="flex items-center gap-1.5"><MapPin className="size-4 text-ink-400" />{t.home_area_name}</span>}
              </div>
            </div>
            <div className="shrink-0 rounded-3xl bg-ink-50/80 p-6 text-center md:w-60">
              <p className="font-display text-4xl font-bold text-ink-950">{naira(t.hourly_rate_kobo)}</p>
              <p className="text-sm text-ink-500">per hour</p>
              <div className="mt-4"><RequestTutorButton tutorId={t.id} /></div>
            </div>
          </motion.div>
        </div>
      </section>
      <div className="mx-auto grid max-w-6xl gap-6 px-4 pb-16 sm:px-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Card title={`About ${t.name.split(" ")[0]}`} icon={BookOpen}>
            <p className="leading-relaxed whitespace-pre-line text-ink-700">{t.bio}</p>
            {t.highest_qualification && <p className="mt-4 flex items-center gap-2 text-sm text-ink-600"><GraduationCap className="size-4 text-brand-500" />{t.highest_qualification} · {t.years_experience} years' teaching experience</p>}
          </Card>
          <Card title="What parents say" icon={Quote}>
            {!t.reviews?.length && <p className="text-ink-500">No reviews yet — reviews can only be left after a confirmed lesson.</p>}
            <ul className="space-y-4">
              {t.reviews?.map((r, i) => (
                <li key={i} className="rounded-2xl bg-ink-50/70 p-4">
                  <div className="flex items-center justify-between gap-2"><span className="flex items-center gap-2"><Avatar name={r.author} size={30} /><span className="font-semibold text-ink-900">{r.author}</span></span><Stars value={r.rating} /></div>
                  {r.comment && <p className="mt-2 text-ink-700">{r.comment}</p>}
                  <p className="mt-1 text-xs text-ink-400">{dateOnly(r.created_at)}</p>
                </li>
              ))}
            </ul>
          </Card>
        </div>
        <div className="space-y-6">
          <Card title="Verified by TutorBridge">
            <ul className="space-y-2.5">
              {t.badges.map((b) => <li key={b} className="flex items-center gap-2.5 text-sm font-medium text-ink-800"><span className="flex size-6 items-center justify-center rounded-full bg-brand-50"><BadgeCheck className="size-4 text-brand-600" /></span>{b}</li>)}
            </ul>
          </Card>
          <Card title="Teaches">
            <ul className="space-y-3">
              {Object.entries(bySubject).map(([s, lv]) => <li key={s}><p className="font-semibold text-ink-900">{s}</p><div className="mt-1 flex flex-wrap gap-1">{lv.map((l) => <Badge key={l}>{l}</Badge>)}</div></li>)}
            </ul>
            <div className="mt-5 space-y-1.5 border-t border-ink-100 pt-4 text-sm text-ink-600">
              <p><span className="text-ink-400">Curricula:</span> {t.curricula.join(", ") || "—"}</p>
              <p><span className="text-ink-400">Areas:</span> {t.areas.join(", ") || "—"}</p>
              {t.offers_online && <p>Also teaches online</p>}
            </div>
          </Card>
          <div className="flex gap-3 rounded-3xl bg-brand-950 p-5 text-sm text-brand-100/80">
            <Lock className="mt-0.5 size-5 shrink-0 text-gold-300" />
            <p>For everyone's safety, contact details are never shared. Booking, payments and messages all happen on TutorBridge — so our guarantee covers you.</p>
          </div>
        </div>
      </div>
    </>
  );
}
