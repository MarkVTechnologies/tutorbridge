import { Check, Copy, Gift, MessageCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "react-toastify";

import { naira } from "@/lib/format";
import { useApi } from "@/lib/hooks";

type Referrals = { code: string; link: string; enabled: boolean; credit_kobo: number; invited: number; rewarded: number; earned_kobo: number };

/** PAY-10: share a referral link; both sides earn a credit when the referred family completes their first package. */
export function ReferralCard({ audience }: { audience: "parent" | "tutor" }) {
  const { data } = useApi<Referrals>("/referrals/", ["referrals"]);
  const [copied, setCopied] = useState(false);
  if (!data || !data.enabled) return null;
  const amount = naira(data.credit_kobo);
  const message = audience === "parent"
    ? `I use TutorBridge for vetted home tutors in Lagos — every tutor is ID- and background-checked. Sign up with my link and we both get ${amount} credit: ${data.link}`
    : `Looking for a vetted home tutor in Lagos? TutorBridge checks every tutor and only charges for lessons delivered. Sign up with my link: ${data.link}`;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(data.link);
      setCopied(true);
      toast.success("Link copied");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Couldn't copy — select the link and copy it manually");
    }
  };
  return (
    <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-gold-100 via-gold-50 to-white p-6 ring-1 ring-gold-200">
      <div className="absolute -top-10 -right-10 size-40 rounded-full bg-gold-300/30 blur-2xl" />
      <div className="relative">
        <div className="flex items-center gap-3">
          <span className="flex size-11 items-center justify-center rounded-2xl bg-gold-300 text-ink-950"><Gift className="size-5" /></span>
          <div>
            <p className="font-display text-lg font-bold text-ink-950">Give {amount}, get {amount}</p>
            <p className="text-sm text-ink-600">
              {audience === "parent" ? "Invite a family. When they complete their first package, you both get wallet credit." : "Refer a family. When they complete their first package, you earn " + amount + " and they get " + amount + " credit."}
            </p>
          </div>
        </div>
        <div className="mt-4 flex items-center gap-2 rounded-2xl bg-white p-1.5 pl-4 ring-1 ring-gold-200">
          <span className="min-w-0 flex-1 truncate font-mono text-sm text-ink-700" title={data.link}>{data.link.replace(/^https?:\/\//, "")}</span>
          <button onClick={copy} className="inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-ink-950 px-3 py-2 text-xs font-semibold text-white hover:bg-ink-800">
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}{copied ? "Copied" : "Copy"}
          </button>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <a href={`https://wa.me/?text=${encodeURIComponent(message)}`} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-xl bg-[#25D366] px-3.5 py-2 text-sm font-semibold text-white hover:brightness-95">
            <MessageCircle className="size-4" /> Share on WhatsApp
          </a>
          <p className="text-xs text-ink-500">{data.invited} joined · {data.rewarded} rewarded · {naira(data.earned_kobo)} earned</p>
        </div>
      </div>
    </section>
  );
}
