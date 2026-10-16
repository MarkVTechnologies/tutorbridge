import { CalendarPlus, Copy, RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "react-toastify";

import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";

import { Alert, Button, Modal } from "./ui";

type Feed = { url: string; webcal: string };

/** BKG-05: subscribe to lessons in Google / Apple / Outlook calendar via a private iCal feed. */
export function CalendarButton() {
  const [open, setOpen] = useState(false);
  const { data } = useApi<Feed>(open ? "/calendar/" : null, ["calendar"]);
  const reset = useAction(() => api.post<Feed>("/calendar/reset/"), [["calendar"]], { success: "New calendar link created — the old one no longer works" });
  const copy = async () => {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(data.url);
      toast.success("Calendar link copied");
    } catch {
      toast.error("Couldn't copy — select the link and copy it manually");
    }
  };
  return (
    <>
      <Button variant="secondary" icon={CalendarPlus} onClick={() => setOpen(true)}>Add to calendar</Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Add lessons to your calendar"
        description="Lessons appear in your calendar and update automatically when they're booked, moved or cancelled.">
        {!data ? <p className="text-sm text-ink-500">Preparing your link…</p> : (
          <>
            <div className="grid gap-2 sm:grid-cols-2">
              <a className="flex min-h-12 items-center justify-center gap-2 rounded-2xl bg-white px-4 text-sm font-semibold text-ink-800 shadow-soft ring-1 ring-ink-200 hover:bg-ink-50"
                href={`https://calendar.google.com/calendar/render?cid=${encodeURIComponent(data.webcal)}`} target="_blank" rel="noreferrer">Google Calendar</a>
              <a className="flex min-h-12 items-center justify-center gap-2 rounded-2xl bg-white px-4 text-sm font-semibold text-ink-800 shadow-soft ring-1 ring-ink-200 hover:bg-ink-50"
                href={data.webcal}>Apple / Outlook</a>
            </div>
            <div>
              <p className="mb-1.5 text-[13px] font-semibold text-ink-700">Or paste this link into any calendar app</p>
              <div className="flex items-center gap-2 rounded-2xl bg-ink-50 p-1.5 pl-3 ring-1 ring-ink-200">
                <span className="min-w-0 flex-1 truncate font-mono text-xs text-ink-600">{data.url}</span>
                <Button size="sm" variant="dark" icon={Copy} onClick={copy}>Copy</Button>
              </div>
            </div>
            <Alert tone="blue">This link is private to you. Check-in codes and your full address are never included. If you shared it by mistake, create a new one.</Alert>
            <Button variant="ghost" size="sm" icon={RefreshCw} loading={reset.isPending} onClick={() => reset.mutate()}>Create a new link</Button>
          </>
        )}
      </Modal>
    </>
  );
}
