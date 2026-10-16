import { Eye, FileText, HelpCircle, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { Markdown } from "@/components/Markdown";
import { Badge, Button, Card, Checkbox, EmptyState, ErrorAlert, Input, Loading, Modal, PageHeader, Select, Tabs, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { dateOnly } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";

type Faq = { id: number; audience: "parent" | "tutor" | "general"; question: string; answer: string; order: number; is_published: boolean };
type Post = { id: number; slug: string; title: string; excerpt: string; body: string; is_published: boolean; published_at: string | null; created_at: string };

export function ContentManager() {
  const [tab, setTab] = useState<"faqs" | "blog">("faqs");
  return (
    <div>
      <PageHeader eyebrow="Website" title="Content" subtitle="FAQs and blog posts on the public site. Changes go live immediately when published."
        actions={<Tabs value={tab} onChange={setTab} options={[{ value: "faqs", label: "FAQs" }, { value: "blog", label: "Blog" }]} />} />
      {tab === "faqs" ? <Faqs /> : <Blog />}
    </div>
  );
}

const AUDIENCES = [["parent", "Parents"], ["tutor", "Tutors"], ["general", "General"]] as const;

function Faqs() {
  const { data, isLoading } = useApi<Faq[]>("/staff/content/faqs/", ["staff-faqs"]);
  const [editing, setEditing] = useState<Partial<Faq> | null>(null);
  const save = useAction((f: Partial<Faq>) => (f.id ? api.patch(`/staff/content/faqs/${f.id}/`, f) : api.post("/staff/content/faqs/", f)), [["staff-faqs"]], { success: "FAQ saved" });
  const remove = useAction((id: number) => api.del(`/staff/content/faqs/${id}/`), [["staff-faqs"]], { success: "FAQ deleted" });
  if (isLoading) return <Loading />;
  return (
    <div className="space-y-6">
      <div className="flex justify-end"><Button icon={Plus} onClick={() => setEditing({ audience: "parent", order: (data?.length ?? 0) + 1, is_published: true })}>New FAQ</Button></div>
      {AUDIENCES.map(([aud, label]) => {
        const items = (data ?? []).filter((f) => f.audience === aud).sort((a, b) => a.order - b.order);
        return (
          <Card key={aud} title={label} icon={HelpCircle}>
            {!items.length && <p className="text-sm text-ink-500">No FAQs for {label.toLowerCase()} yet.</p>}
            <ul className="divide-y divide-ink-100">
              {items.map((f) => (
                <li key={f.id} className="flex items-start justify-between gap-4 py-3">
                  <div className="min-w-0">
                    <p className="font-semibold text-ink-900"><span className="mr-2 text-xs text-ink-400">#{f.order}</span>{f.question}{!f.is_published && <Badge className="ml-2">Hidden</Badge>}</p>
                    <p className="mt-0.5 line-clamp-2 text-sm text-ink-500">{f.answer}</p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button size="sm" variant="ghost" icon={Pencil} onClick={() => setEditing(f)}>Edit</Button>
                    <Button size="sm" variant="ghost" className="text-red-600" icon={Trash2} onClick={() => remove.mutate(f.id)} aria-label={`Delete ${f.question}`} />
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        );
      })}
      {editing && (
        <Modal open onClose={() => setEditing(null)} title={editing.id ? "Edit FAQ" : "New FAQ"}
          footer={<Button loading={save.isPending} onClick={() => save.mutate(editing, { onSuccess: () => setEditing(null) })}>Save</Button>}>
          <ErrorAlert error={save.error} />
          <div className="grid grid-cols-2 gap-3">
            <Select label="Shown to" value={editing.audience} onChange={(e) => setEditing({ ...editing, audience: e.target.value as Faq["audience"] })}>
              {AUDIENCES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
            <Input label="Order" type="number" min={0} value={editing.order ?? 0} onChange={(e) => setEditing({ ...editing, order: Number(e.target.value) })} />
          </div>
          <Input label="Question" value={editing.question ?? ""} onChange={(e) => setEditing({ ...editing, question: e.target.value })} error={save.error?.field("question")} />
          <Textarea label="Answer" value={editing.answer ?? ""} onChange={(e) => setEditing({ ...editing, answer: e.target.value })} error={save.error?.field("answer")} />
          <Checkbox label="Published" checked={!!editing.is_published} onChange={(e) => setEditing({ ...editing, is_published: e.target.checked })} />
        </Modal>
      )}
    </div>
  );
}

function Blog() {
  const { data, isLoading } = useApi<Post[]>("/staff/content/posts/", ["staff-posts"]);
  const [editing, setEditing] = useState<Partial<Post> | null>(null);
  const [preview, setPreview] = useState(false);
  const save = useAction((p: Partial<Post>) => (p.id ? api.patch(`/staff/content/posts/${p.id}/`, p) : api.post("/staff/content/posts/", p)), [["staff-posts"]], { success: "Post saved" });
  const remove = useAction((id: number) => api.del(`/staff/content/posts/${id}/`), [["staff-posts"]], { success: "Post deleted" });
  if (isLoading) return <Loading />;
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Button icon={Plus} onClick={() => { setPreview(false); setEditing({ is_published: false, body: "" }); }}>New post</Button></div>
      {!data?.length && <EmptyState icon={FileText} title="No posts yet">Exam countdowns, study tips and tutor spotlights help families find you through search.</EmptyState>}
      {data?.map((p) => (
        <Card key={p.id}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-display text-lg font-bold text-ink-950">{p.title}</p>
              <p className="text-sm text-ink-500">/blog/{p.slug} · {p.is_published ? `Published ${dateOnly(p.published_at)}` : "Draft"}</p>
              {p.excerpt && <p className="mt-1 text-sm text-ink-600">{p.excerpt}</p>}
            </div>
            <div className="flex gap-1">
              {p.is_published ? <Badge tone="green" dot>Live</Badge> : <Badge dot>Draft</Badge>}
              {p.is_published && <a href={`/blog/${p.slug}`} target="_blank" rel="noreferrer" className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-3 text-[13px] font-semibold text-brand-700 hover:bg-brand-50"><Eye className="size-4" />View</a>}
              <Button size="sm" variant="ghost" icon={Pencil} onClick={() => { setPreview(false); setEditing(p); }}>Edit</Button>
              <Button size="sm" variant="ghost" className="text-red-600" icon={Trash2} onClick={() => remove.mutate(p.id)} aria-label={`Delete ${p.title}`} />
            </div>
          </div>
        </Card>
      ))}
      {editing && (
        <Modal open onClose={() => setEditing(null)} title={editing.id ? "Edit post" : "New post"}
          footer={<>
            <Button variant="secondary" icon={Eye} onClick={() => setPreview((v) => !v)}>{preview ? "Edit" : "Preview"}</Button>
            <Button loading={save.isPending} onClick={() => save.mutate(editing, { onSuccess: () => setEditing(null) })}>{editing.is_published ? "Save & publish" : "Save draft"}</Button>
          </>}>
          <ErrorAlert error={save.error} />
          {preview ? (
            <div><h1 className="mb-4 font-display text-2xl font-bold">{editing.title}</h1><Markdown text={editing.body ?? ""} /></div>
          ) : (
            <>
              <Input label="Title" value={editing.title ?? ""} onChange={(e) => setEditing({ ...editing, title: e.target.value })} error={save.error?.field("title")} />
              <Input label="URL slug (optional)" hint="Leave blank to generate from the title." value={editing.slug ?? ""} onChange={(e) => setEditing({ ...editing, slug: e.target.value })} error={save.error?.field("slug")} />
              <Input label="Excerpt" hint="One or two sentences shown on the blog index and in search results." value={editing.excerpt ?? ""} onChange={(e) => setEditing({ ...editing, excerpt: e.target.value })} />
              <Textarea label="Body" hint="## Heading · - list item · **bold** · *italic* · [link text](https://...)" className="min-h-64 font-mono text-sm"
                value={editing.body ?? ""} onChange={(e) => setEditing({ ...editing, body: e.target.value })} error={save.error?.field("body")} />
              <Checkbox label="Published (visible on the public blog)" checked={!!editing.is_published} onChange={(e) => setEditing({ ...editing, is_published: e.target.checked })} />
            </>
          )}
        </Modal>
      )}
    </div>
  );
}
