import type { QueryKey } from "@tanstack/react-query";
import { useState } from "react";

import { Alert, Button, ErrorAlert, Input, Modal, Select, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useAction, useRefData } from "@/lib/hooks";
import type { Lesson } from "@/lib/types";

type Dialog = null | "cancel" | "reschedule" | "dispute" | "safety";

export function LessonActions({ lesson: l, invalidate }: { lesson: Lesson; invalidate: QueryKey[] }) {
  const { me } = useAuth();
  const { data: ref } = useRefData();
  const isParent = me?.role === "parent";
  const [dialog, setDialog] = useState<Dialog>(null);
  const [reason, setReason] = useState("");
  const [start, setStart] = useState("");
  const [disputeReason, setDisputeReason] = useState("quality");
  const [msg, setMsg] = useState<string | null>(null);
  const confirmLesson = useAction(() => api.post(`/lessons/${l.id}/confirm/`), invalidate);
  const cancel = useAction(() => api.post(`/lessons/${l.id}/cancel/`, { reason }), invalidate);
  const reschedule = useAction(() => api.post(`/lessons/${l.id}/reschedule/`, { start }), invalidate);
  const dispute = useAction(() => api.post(`/lessons/${l.id}/dispute/`, { reason: disputeReason, description: reason }), invalidate);
  const safety = useAction(() => api.post<{ detail: string }>(`/lessons/${l.id}/safety-report/`, { description: reason }));
  const close = () => { setDialog(null); setReason(""); };
  const hoursToStart = (new Date(l.scheduled_start).getTime() - Date.now()) / 3600000;
  const lateNotice = hoursToStart < (ref?.config.late_cancel_notice_hours ?? 24);
  const upcoming = l.status === "scheduled";
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {isParent && l.status === "completed" && (
        <Button loading={confirmLesson.isPending} onClick={() => confirmLesson.mutate()}>Confirm lesson</Button>
      )}
      {upcoming && <Button variant="ghost" onClick={() => setDialog("cancel")}>Cancel</Button>}
      {upcoming && !lateNotice && <Button variant="ghost" onClick={() => setDialog("reschedule")}>Reschedule</Button>}
      {l.can_dispute && !l.dispute_status && <Button variant="ghost" onClick={() => setDialog("dispute")}>Report a problem</Button>}
      {(upcoming || l.status === "in_progress") && <Button variant="ghost" className="text-red-700" onClick={() => setDialog("safety")}>⚠ Safety</Button>}
      {l.dispute_status && <span className="self-center text-sm text-amber-700">Dispute {l.dispute_status} — payment for this lesson is on hold.</span>}
      <ErrorAlert error={confirmLesson.error} />
      {msg && <Alert tone="green">{msg}</Alert>}

      <Modal open={dialog === "cancel"} onClose={close} title="Cancel this lesson?"
        footer={<><Button variant="secondary" onClick={close}>Keep lesson</Button><Button variant="danger" loading={cancel.isPending} onClick={() => cancel.mutate(undefined, { onSuccess: close })}>Cancel lesson</Button></>}>
        {isParent ? (
          lateNotice
            ? <Alert tone="amber">This lesson starts in less than {ref?.config.late_cancel_notice_hours ?? 24} hours, so {ref?.config.late_cancel_tutor_pct ?? 50}% of the fee will be paid to the tutor for their time. The rest returns to your wallet.</Alert>
            : <Alert tone="green">The full lesson fee will return to your wallet.</Alert>
        ) : (
          <Alert tone="amber">The parent gets a full refund.{lateNotice && " Cancelling with less than 24 hours' notice adds a strike to your record."}</Alert>
        )}
        <ErrorAlert error={cancel.error} />
        <Textarea label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Modal>

      <Modal open={dialog === "reschedule"} onClose={close} title="Reschedule lesson"
        footer={<Button loading={reschedule.isPending} disabled={!start} onClick={() => reschedule.mutate(undefined, { onSuccess: close })}>Reschedule</Button>}>
        <ErrorAlert error={reschedule.error} />
        <Input label="New date and time" type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} hint="Lagos time. Please agree the new time with the other party in Messages first." />
      </Modal>

      <Modal open={dialog === "dispute"} onClose={close} title="Report a problem with this lesson"
        footer={<Button variant="danger" loading={dispute.isPending} onClick={() => dispute.mutate(undefined, { onSuccess: close })}>Submit</Button>}>
        <p className="text-sm text-slate-600">Payment for this lesson will be frozen until our team resolves it — usually within 2 working days.</p>
        <ErrorAlert error={dispute.error} />
        <Select label="What happened?" value={disputeReason} onChange={(e) => setDisputeReason(e.target.value)}>
          <option value="quality">Lesson quality</option><option value="late">Tutor was late / left early</option><option value="not_delivered">Lesson didn't happen</option><option value="conduct">Conduct concern</option><option value="other">Other</option>
        </Select>
        <Textarea label="Details" required value={reason} onChange={(e) => setReason(e.target.value)} />
      </Modal>

      <Modal open={dialog === "safety"} onClose={close} title="Urgent safety report"
        footer={<Button variant="danger" loading={safety.isPending} onClick={() => safety.mutate(undefined, { onSuccess: (r) => { close(); setMsg(r.detail); } })}>Alert the safety team now</Button>}>
        <Alert>If anyone is in immediate danger, call <strong>112</strong> first.</Alert>
        <p className="text-sm text-slate-600">Our on-call safety officer is alerted immediately by SMS and email.</p>
        <ErrorAlert error={safety.error} />
        <Textarea label="What is happening?" required value={reason} onChange={(e) => setReason(e.target.value)} />
      </Modal>
    </div>
  );
}
