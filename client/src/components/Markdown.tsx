import { Fragment, type ReactNode } from "react";

/**
 * Minimal, safe Markdown for blog posts: ## headings, paragraphs, "- " lists, **bold**, *italic*
 * and [links](https://...). Builds React elements (never innerHTML), so HTML in a post is shown
 * as text, not executed. Only http(s) and site-relative links are allowed.
 */
export function Markdown({ text }: { text: string }) {
  const blocks = text.replace(/\r\n/g, "\n").split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
  return (
    <div className="space-y-5 text-[17px] leading-relaxed text-ink-700">
      {blocks.map((block, i) => {
        const lines = block.split("\n");
        if (/^###\s/.test(block)) return <h3 key={i} className="pt-2 font-display text-xl font-bold text-ink-950">{inline(block.replace(/^###\s/, ""))}</h3>;
        if (/^##\s/.test(block)) return <h2 key={i} className="pt-4 font-display text-2xl font-bold text-ink-950">{inline(block.replace(/^##\s/, ""))}</h2>;
        if (lines.every((l) => /^[-*]\s/.test(l))) {
          return (
            <ul key={i} className="space-y-2 pl-1">
              {lines.map((l, j) => <li key={j} className="flex gap-3"><span className="mt-2.5 size-1.5 shrink-0 rounded-full bg-brand-500" /><span>{inline(l.replace(/^[-*]\s/, ""))}</span></li>)}
            </ul>
          );
        }
        if (lines.every((l) => /^\d+\.\s/.test(l))) {
          return <ol key={i} className="list-decimal space-y-2 pl-6">{lines.map((l, j) => <li key={j}>{inline(l.replace(/^\d+\.\s/, ""))}</li>)}</ol>;
        }
        return <p key={i}>{lines.map((l, j) => <Fragment key={j}>{j > 0 && <br />}{inline(l)}</Fragment>)}</p>;
      })}
    </div>
  );
}

const TOKEN = /(\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)\s]+\))/g;

function inline(text: string): ReactNode[] {
  return text.split(TOKEN).filter(Boolean).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i} className="font-semibold text-ink-900">{part.slice(2, -2)}</strong>;
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) return <em key={i}>{part.slice(1, -1)}</em>;
    const link = part.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/);
    if (link) {
      const href = link[2];
      const safe = /^https?:\/\//i.test(href) || href.startsWith("/");
      return safe
        ? <a key={i} href={href} className="font-medium text-brand-700 underline underline-offset-2" {...(href.startsWith("/") ? {} : { target: "_blank", rel: "noreferrer" })}>{link[1]}</a>
        : <Fragment key={i}>{link[1]}</Fragment>;
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}
