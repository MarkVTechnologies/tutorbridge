import { ArrowRight, BadgeCheck, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { Autoplay, Pagination as SwiperPagination } from "swiper/modules";
import { Swiper, SwiperSlide } from "swiper/react";
import "swiper/css";
import "swiper/css/pagination";

import { SectionHeading } from "@/components/marketing";
import { Avatar, Badge, ButtonLink, Reveal, Stars, TierBadge } from "@/components/ui";
import type { Paginated } from "@/lib/api";
import { naira } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { TutorPublic } from "@/lib/types";

export default function FeaturedTutors() {
  const { data } = useApi<Paginated<TutorPublic>>("/tutors/?sort=rating");
  const tutors = data?.results ?? [];
  if (!tutors.length) return null;
  return (
    <section className="py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <SectionHeading align="left" eyebrow="Meet the tutors" title="Real teachers. Verified, every one." />
          <ButtonLink to="/tutors" variant="secondary" iconRight={ArrowRight}>Browse all tutors</ButtonLink>
        </div>
        <Reveal className="mt-12">
          <Swiper modules={[Autoplay, SwiperPagination]} spaceBetween={20} slidesPerView={1.1} pagination={{ clickable: true }}
            autoplay={{ delay: 5000, disableOnInteraction: true, pauseOnMouseEnter: true }}
            breakpoints={{ 640: { slidesPerView: 2.1 }, 1024: { slidesPerView: 3 } }} className="!pb-12">
            {tutors.map((t) => (
              <SwiperSlide key={t.id} className="!h-auto">
                <TutorSlide t={t} />
              </SwiperSlide>
            ))}
          </Swiper>
        </Reveal>
      </div>
    </section>
  );
}

function TutorSlide({ t }: { t: TutorPublic }) {
  const subjects = [...new Set(t.subjects.map((s) => s.subject_name))];
  return (
    <Link to={`/tutors/${t.id}`} className="group flex h-full flex-col rounded-[2rem] border border-ink-100 bg-white p-6 shadow-soft transition hover:-translate-y-1 hover:shadow-lift">
      <div className="flex items-start justify-between">
        <Avatar name={t.name} src={t.photo_url} size={64} />
        <TierBadge tier={t.tier} />
      </div>
      <h3 className="mt-4 flex items-center gap-1.5 font-display text-xl font-bold text-ink-950">{t.name} <BadgeCheck className="size-5 fill-brand-500 text-white" /></h3>
      <p className="mt-1 line-clamp-2 text-sm text-ink-500">{t.headline}</p>
      <div className="mt-4 flex flex-wrap gap-1.5">{subjects.slice(0, 3).map((s) => <Badge key={s} tone="green">{s}</Badge>)}</div>
      <div className="mt-auto flex items-center justify-between border-t border-ink-100 pt-4 text-sm">
        <span className="flex items-center gap-1.5 text-ink-600">
          {t.rating_count ? <><Stars value={Number(t.rating_avg)} /> {Number(t.rating_avg).toFixed(1)}</> : <><Sparkles className="size-4 text-gold-500" /> New tutor</>}
        </span>
        <span className="font-display font-bold text-ink-950">{naira(t.hourly_rate_kobo)}<span className="text-xs font-normal text-ink-500">/hr</span></span>
      </div>
    </Link>
  );
}

