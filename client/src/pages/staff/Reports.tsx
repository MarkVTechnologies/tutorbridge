import { AlertTriangle, CheckCircle2, Download, MinusCircle, Table2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Card, EmptyState, Loading, PageHeader, Table, Tabs, Td } from "@/components/ui";
import { cn } from "@/lib/cn";
import { dateOnly, naira } from "@/lib/format";
import { useApi } from "@/lib/hooks";

type Metric = { key: string; label: string; value: number | null; unit: string; target: string; on_target: boolean | null; n: number; hint: string };
type Week = { week: string; requests: number; bookings: number; lessons: number; gmv_kobo: number; fill_rate: number | null };
type Report = {
  generated_at: string; days: number; scorecard: Metric[]; weekly: Week[];
  cohorts: { cohort: string; size: number; retention: (number | null)[] }[];
  areas: { area: string; requests: number; filled: number; fill_rate: number | null }[];
};

const PERIODS = ["7", "30", "90", "180"] as const;
// Chart tokens. Series hue is brand-500 (validated: lightness band, chroma, 3:1 vs surface).
const SERIES = "var(--color-brand-500)";
const GRID = "var(--color-ink-100)";
const AXIS_TEXT = "var(--color-ink-500)";
const SEQ = ["#ecf8f2", "#d2efe0", "#a6dec3", "#6fc59f", "#3ca77b", "#1d8a60", "#136f4c", "#0f593e"]; // brand-50 → 700, light → dark

const compact = (v: number) => (v >= 1e6 ? `${+(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${+(v / 1e3).toFixed(1)}K` : `${+v.toFixed(1)}`);
const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;
const weekLabel = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("en-NG", { day: "numeric", month: "short" });

/** ADM-07: pilot scorecard against the PRD section 20 targets, trends, cohorts, fill rate by area. */
export function Reports() {
  const [days, setDays] = useState<(typeof PERIODS)[number]>("30");
  const { data, isLoading } = useApi<Report>(`/staff/reports/?days=${days}`, ["staff-reports", days]);
  return (
    <div className="max-w-6xl">
      <PageHeader eyebrow="Pilot" title="Reports" subtitle="Success metrics against the pilot targets, with trends and retention."
        actions={<>
          <Tabs value={days} onChange={setDays} options={PERIODS.map((d) => ({ value: d, label: <span className="whitespace-nowrap" aria-label={`${d} days`}>{d}d</span> }))} />
          <a href={`/api/staff/reports/?days=${days}&export=csv`} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-white px-4 text-sm font-semibold text-ink-800 shadow-soft ring-1 ring-ink-200 transition hover:bg-ink-50">
            <Download className="size-4" />CSV
          </a>
        </>} />
      {isLoading && <Loading />}
      {data && <>
        <section aria-label="Scorecard" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {data.scorecard.map((m) => <MetricTile key={m.key} m={m} />)}
        </section>
        <p className="mt-2 text-xs text-ink-500">Last {data.days} days · generated {dateOnly(data.generated_at)}. Fill rate only counts requests at least 48 hours old.</p>
        <Trends weeks={data.weekly} />
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <Cohorts rows={data.cohorts} />
          <Areas rows={data.areas} />
        </div>
      </>}
    </div>
  );
}

function MetricTile({ m }: { m: Metric }) {
  const status = m.on_target === null ? { icon: MinusCircle, text: "No data yet", cls: "text-ink-500" }
    : m.on_target ? { icon: CheckCircle2, text: "On target", cls: "text-brand-700" } : { icon: AlertTriangle, text: "Off target", cls: "text-amber-700" };
  const Icon = status.icon;
  return (
    <div className={cn("rounded-2xl bg-white p-4 shadow-soft ring-1", m.on_target === false ? "ring-amber-200" : "ring-ink-100")}>
      <p className="text-sm font-medium text-ink-600">{m.label}</p>
      <p className="mt-1 font-sans text-3xl font-semibold text-ink-950 tabular-nums">{m.value === null ? "—" : `${m.value}${m.unit}`}</p>
      <p className={cn("mt-2 flex items-center gap-1.5 text-xs font-semibold", status.cls)}><Icon className="size-3.5" />{status.text} <span className="font-normal text-ink-500">· target {m.target}</span></p>
      <p className="mt-1 text-xs text-ink-500" title={m.hint}>{m.hint ? `${m.hint}. ` : ""}n = {m.n}</p>
    </div>
  );
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

function niceMax(v: number) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 2, 2.5, 5, 10].map((s) => s * p).find((s) => s >= v) ?? v;
}

type Point = { label: string; value: number | null };
const H = 180, PAD = { t: 16, r: 12, b: 26, l: 40 };

/** Single-series chart: columns (magnitude) or a line (a rate), with optional target reference and hover tooltip. */
function MiniChart({ title, points, kind, format, target, max: fixedMax }: { title: string; points: Point[]; kind: "column" | "line"; format: (v: number) => string; target?: number; max?: number }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const values = points.map((p) => p.value ?? 0);
  const max = fixedMax ?? Math.max(niceMax(Math.max(...values, target ?? 0)), 2);
  const iw = Math.max(width - PAD.l - PAD.r, 10), ih = H - PAD.t - PAD.b;
  const band = iw / points.length;
  const x = (i: number) => PAD.l + band * i + band / 2;
  const y = (v: number) => PAD.t + ih - (v / max) * ih;
  const barW = Math.min(24, band - 2);
  const ticks = Number.isInteger(max / 2) || max > 10 ? [0, max / 2, max] : [0, max];
  const last = points.length - 1;
  const line = points.map((p, i) => (p.value === null ? null : `${x(i)},${y(p.value)}`));
  const segments: string[][] = [];
  line.forEach((pt) => { if (pt === null) segments.push([]); else (segments.at(-1) ?? segments[segments.push([]) - 1]).push(pt); });
  const lastVal = [...points].reverse().find((p) => p.value !== null);
  const lastIdx = lastVal ? points.lastIndexOf(lastVal) : -1;
  return (
    <figure className="min-w-0">
      <figcaption className="mb-1 text-sm font-semibold text-ink-800">{title}</figcaption>
      <div ref={ref} className="relative" onMouseLeave={() => setHover(null)}>
        {width > 0 && (
          <svg width={width} height={H} role="img" aria-label={`${title}, weekly. Latest: ${lastVal?.value != null ? format(lastVal.value) : "no data"}.`}>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={PAD.l} x2={width - PAD.r} y1={y(t)} y2={y(t)} stroke={GRID} strokeWidth={1} />
                <text x={PAD.l - 6} y={y(t)} dy="0.32em" textAnchor="end" fontSize={11} fill={AXIS_TEXT}>{compact(t)}</text>
              </g>
            ))}
            {target !== undefined && (
              <g>
                <line x1={PAD.l} x2={width - PAD.r} y1={y(target)} y2={y(target)} stroke="var(--color-ink-400)" strokeWidth={1} />
                <text x={width - PAD.r} y={y(target) - 4} textAnchor="end" fontSize={11} fill={AXIS_TEXT}>target {target}%</text>
              </g>
            )}
            {kind === "column" && points.map((p, i) => {
              const v = p.value ?? 0, top = y(v), h = PAD.t + ih - top, r = Math.min(4, h);
              const x0 = x(i) - barW / 2;
              return v > 0 ? (
                <path key={i} fill={SERIES} opacity={hover === null || hover === i ? 1 : 0.55}
                  d={`M${x0},${PAD.t + ih} V${top + r} Q${x0},${top} ${x0 + r},${top} H${x0 + barW - r} Q${x0 + barW},${top} ${x0 + barW},${top + r} V${PAD.t + ih} Z`} />
              ) : null;
            })}
            {kind === "line" && <>
              {segments.filter((s) => s.length).map((s, k) => <polyline key={k} points={s.join(" ")} fill="none" stroke={SERIES} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />)}
              {points.map((p, i) => p.value !== null && (i === hover || i === lastIdx) && (
                <circle key={i} cx={x(i)} cy={y(p.value)} r={4.5} fill={SERIES} stroke="white" strokeWidth={2} />
              ))}
              {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={PAD.t + ih} stroke="var(--color-ink-300)" strokeWidth={1} />}
            </>}
            {lastIdx >= 0 && lastVal?.value != null && hover === null && (
              <text x={Math.min(x(lastIdx), width - PAD.r)} y={y(lastVal.value) - 8} textAnchor="end" fontSize={11} fontWeight={600} fill="var(--color-ink-800)">{format(lastVal.value)}</text>
            )}
            {points.map((p, i) => (i === 0 || i === last || i === Math.floor(last / 2)) && (
              <text key={i} x={x(i)} y={H - 8} textAnchor={i === 0 ? "start" : i === last ? "end" : "middle"} fontSize={11} fill={AXIS_TEXT}>{p.label}</text>
            ))}
            {points.map((_, i) => (
              <rect key={i} x={PAD.l + band * i} y={0} width={band} height={H} fill="transparent" onMouseEnter={() => setHover(i)} onTouchStart={() => setHover(i)} />
            ))}
          </svg>
        )}
        {hover !== null && width > 0 && (
          <div className="pointer-events-none absolute top-0 z-10 rounded-lg bg-ink-950 px-2.5 py-1.5 text-xs whitespace-nowrap text-white shadow-lift"
            style={{ left: Math.min(Math.max(x(hover) - 60, 0), width - 130) }}>
            <p className="text-white/70">Week of {points[hover].label}</p>
            <p className="font-semibold">{points[hover].value === null ? "No data" : format(points[hover].value!)}</p>
          </div>
        )}
      </div>
    </figure>
  );
}

function Trends({ weeks }: { weeks: Week[] }) {
  const [table, setTable] = useState(false);
  const pts = (f: (w: Week) => number | null) => weeks.map((w) => ({ label: weekLabel(w.week), value: f(w) }));
  return (
    <Card className="mt-6" title="Weekly trends" subtitle={`Last ${weeks.length} weeks, Monday to Sunday`}
      actions={<button type="button" onClick={() => setTable(!table)} aria-pressed={table} className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm font-medium text-ink-600 hover:bg-ink-50"><Table2 className="size-4" />{table ? "Charts" : "Table"}</button>}>
      {table ? (
        <Table head={["Week of", "Requests", "Paid bookings", "Lessons delivered", "Lesson value", "Fill rate"]}>
          {weeks.map((w) => (
            <tr key={w.week}><Td>{weekLabel(w.week)}</Td><Td>{w.requests}</Td><Td>{w.bookings}</Td><Td>{w.lessons}</Td><Td>{naira(w.gmv_kobo)}</Td><Td>{w.fill_rate === null ? "—" : `${w.fill_rate}%`}</Td></tr>
          ))}
        </Table>
      ) : (
        <div className="grid gap-x-8 gap-y-6 md:grid-cols-2">
          <MiniChart title="Lessons delivered" kind="column" points={pts((w) => w.lessons)} format={(v) => plural(v, "lesson")} />
          <MiniChart title="Lesson value (₦)" kind="column" points={pts((w) => w.gmv_kobo / 100)} format={(v) => naira(v * 100)} />
          <MiniChart title="New requests" kind="column" points={pts((w) => w.requests)} format={(v) => plural(v, "request")} />
          <MiniChart title="Fill rate within 48 h" kind="line" points={pts((w) => w.fill_rate)} format={(v) => `${v}%`} target={80} max={100} />
        </div>
      )}
    </Card>
  );
}

function Cohorts({ rows }: { rows: Report["cohorts"] }) {
  const span = Math.max(0, ...rows.map((r) => r.retention.length));
  const cell = (v: number | null) => SEQ[v === null ? 0 : Math.min(SEQ.length - 1, Math.floor((v / 100) * (SEQ.length - 1) + 0.5))];
  return (
    <Card title="Parent retention" subtitle="Cohort = month of a family's first lesson. Cells show the share with a lesson that month.">
      {!rows.length ? <EmptyState title="No delivered lessons yet" /> : (
        <div className="overflow-x-auto">
          <table className="w-full border-separate border-spacing-0.5 text-center text-xs tabular-nums">
            <thead>
              <tr className="text-ink-500"><th className="px-2 py-1 text-left font-medium">Cohort</th><th className="px-2 py-1 font-medium">Families</th>
                {Array.from({ length: span }, (_, k) => <th key={k} className="px-2 py-1 font-medium">{k === 0 ? "M0" : `+${k}`}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.cohort}>
                  <td className="px-2 py-1.5 text-left font-medium text-ink-800">{new Date(r.cohort + "-01T00:00:00").toLocaleDateString("en-NG", { month: "short", year: "numeric" })}</td>
                  <td className="px-2 py-1.5 text-ink-700">{r.size}</td>
                  {Array.from({ length: span }, (_, k) => {
                    const v = r.retention[k];
                    if (v === undefined) return <td key={k} />;
                    return <td key={k} title={`${r.cohort}, month +${k}: ${v}%`} className={cn("rounded-md px-2 py-1.5 font-semibold", (v ?? 0) >= 60 ? "text-white" : "text-ink-900")} style={{ background: cell(v) }}>{v}%</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function Areas({ rows }: { rows: Report["areas"] }) {
  return (
    <Card title="Fill rate by area" subtitle="In-person requests in the period. Expand a cluster only once it holds the 80% target.">
      {!rows.length ? <EmptyState title="No requests old enough to judge" /> : (
        <ul className="space-y-3">
          {rows.map((a) => (
            <li key={a.area} className="text-sm">
              <div className="flex items-baseline justify-between gap-3">
                <span className="truncate font-medium text-ink-800">{a.area}</span>
                <span className="shrink-0 text-ink-600 tabular-nums"><span className="font-semibold text-ink-900">{a.fill_rate ?? 0}%</span> · {a.filled}/{a.requests}</span>
              </div>
              <div className="relative mt-1.5 h-2 rounded-full bg-brand-50" role="meter" aria-valuenow={a.fill_rate ?? 0} aria-valuemin={0} aria-valuemax={100} aria-label={`${a.area} fill rate`}>
                <div className="h-full rounded-full" style={{ width: `${a.fill_rate ?? 0}%`, background: (a.fill_rate ?? 0) >= 80 ? SERIES : "var(--color-gold-400)" }} />
                <span className="absolute inset-y-[-3px] w-px bg-ink-400" style={{ left: "80%" }} aria-hidden="true" />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
