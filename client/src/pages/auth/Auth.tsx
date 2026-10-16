import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { KeyRound, Lock, Mail, Phone, ShieldCheck, UserRound, Wallet } from "lucide-react";
import { motion } from "@/lib/motion";

import { Logo } from "@/components/Layout";
import { Seo } from "@/components/Seo";
import { Alert, Button, Checkbox, ErrorAlert, Input, Loading, Select, Tabs } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";
import { useAction } from "@/lib/hooks";
import type { Me } from "@/lib/types";

function AuthShell({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-cream">
      <Seo title={title} />
      {/* Brand panel */}
      <aside className="grain relative hidden w-[44%] max-w-[640px] flex-col justify-between overflow-hidden bg-brand-950 p-12 text-white lg:flex">
        <div className="bg-grid pointer-events-none absolute inset-0 opacity-60" />
        <div className="absolute -top-32 -right-32 size-[28rem] rounded-full bg-brand-500/30 blur-3xl" />
        <div className="absolute -bottom-40 -left-24 size-[24rem] rounded-full bg-gold-400/15 blur-3xl" />
        <div className="relative"><Logo light /></div>
        <div className="relative">
          <motion.h2 initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} className="font-display text-4xl leading-tight font-bold text-balance">
            Every tutor checked. <span className="text-gold-300">Every lesson accounted for.</span>
          </motion.h2>
          <ul className="mt-10 space-y-4">
            {([[ShieldCheck, "11-step vetting", "ID, background, interview, tests and references"], [KeyRound, "Check-in codes", "Every lesson started and ended with a code only you see"], [Wallet, "Escrow payments", "Released to the tutor only after each lesson is confirmed"]] as const).map(([Icon, t, d], i) => (
              <motion.li key={t} initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.15 + i * 0.1 }} className="flex gap-4">
                <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-white/10 ring-1 ring-white/10"><Icon className="size-5 text-gold-300" /></span>
                <div><p className="font-semibold">{t}</p><p className="text-sm text-brand-100/70">{d}</p></div>
              </motion.li>
            ))}
          </ul>
        </div>
        <p className="relative text-sm text-brand-100/60">Need help? <Link to="/contact" className="text-gold-300 hover:underline">Contact our team</Link></p>
      </aside>
      {/* Form */}
      <main className="flex flex-1 items-start justify-center px-4 py-10 sm:items-center sm:px-8">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="w-full max-w-[440px]">
          <div className="mb-8 lg:hidden"><Logo /></div>
          <h1 className="font-display text-3xl font-bold text-ink-950">{title}</h1>
          {subtitle && <p className="mt-2 text-ink-500">{subtitle}</p>}
          <div className="mt-8">{children}</div>
        </motion.div>
      </main>
    </div>
  );
}

function safeNext(next: string | null) {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : null;
}

export function Login() {
  const [params] = useSearchParams();
  const { setMe } = useAuth();
  const nav = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"password" | "2fa">("password");
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  const finish = (me: Me) => {
    setMe(me);
    if (me.is_staff_member && (me.needs_2fa_setup || !me.two_factor_ok)) return nav("/account/2fa");
    nav(safeNext(params.get("next")) ?? homeFor(me));
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (step === "password") {
        const r = await api.post<Me | { requires_2fa: true }>("/auth/login/", { identifier, password, remember });
        if ("requires_2fa" in r) setStep("2fa");
        else finish(r);
      } else {
        finish(await api.post<Me>("/auth/login/2fa/", { code }));
      }
    } catch (x) {
      setError(x as ApiError);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title={step === "password" ? "Log in" : "Two-factor authentication"} subtitle={step === "2fa" ? "Enter the 6-digit code from your authenticator app." : undefined}>
      <form onSubmit={submit} className="space-y-4">
        <ErrorAlert error={error} />
        {step === "password" ? (
          <>
            <Input label="Email or phone number" icon={UserRound} autoComplete="username" required value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
            <Input label="Password" icon={Lock} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            <div className="flex items-center justify-between">
              <Checkbox label="Remember me" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
              <Link to="/forgot-password" className="text-sm text-brand-600 hover:underline">Forgot password?</Link>
            </div>
          </>
        ) : (
          <Input label="Authentication code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} required autoFocus value={code} onChange={(e) => setCode(e.target.value)} />
        )}
        <Button type="submit" size="lg" loading={busy} className="w-full">{step === "password" ? "Log in" : "Verify"}</Button>
      </form>
      <p className="mt-4 text-center text-sm text-slate-600">New to TutorBridge? <Link to="/signup" className="font-semibold text-brand-600">Create an account</Link></p>
    </AuthShell>
  );
}

export function Signup() {
  const [params] = useSearchParams();
  const { setMe } = useAuth();
  const nav = useNavigate();
  const [role, setRole] = useState<"parent" | "tutor">(params.get("role") === "tutor" ? "tutor" : "parent");
  const [f, setF] = useState({ first_name: "", last_name: "", email: "", phone: "", gender: "", password: "", consent_terms: false, consent_marketing: false });
  const signup = useAction(() => api.post<Me>("/auth/signup/", { ...f, role }));
  const err = signup.error;
  return (
    <AuthShell title="Create your account" subtitle={role === "parent" ? "Find a vetted tutor for your child." : "Apply to teach with TutorBridge."}>
      <Tabs className="mb-6 flex w-full" value={role} onChange={setRole} options={[{ value: "parent", label: "I'm a parent" }, { value: "tutor", label: "I'm a tutor" }]} />
      <form className="space-y-4" onSubmit={(e) => {
        e.preventDefault();
        signup.mutate(undefined, { onSuccess: (me) => { setMe(me); nav(`/verify${params.get("next") ? `?next=${encodeURIComponent(params.get("next")!)}` : ""}`); } });
      }}>
        {err && !err.field("email") && !err.field("phone") && !err.field("password") && <ErrorAlert error={err} />}
        <div className="grid grid-cols-2 gap-3">
          <Input label="First name" required autoComplete="given-name" value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} error={err?.field("first_name")} />
          <Input label="Last name" required autoComplete="family-name" value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} error={err?.field("last_name")} />
        </div>
        <Input label="Email" icon={Mail} type="email" required autoComplete="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} error={err?.field("email")} />
        <Input label="Phone number" icon={Phone} type="tel" required autoComplete="tel" placeholder="0803 123 4567" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} error={err?.field("phone")} hint="We'll text you a code to verify it." />
        {role === "tutor" && (
          <Select label="Gender" value={f.gender} onChange={(e) => setF({ ...f, gender: e.target.value })} hint="Some families request a tutor of a specific gender.">
            <option value="">Prefer not to say</option><option value="female">Female</option><option value="male">Male</option>
          </Select>
        )}
        <Input label="Password" icon={Lock} type="password" required autoComplete="new-password" minLength={10} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} error={err?.field("password")} hint="At least 10 characters." />
        <Checkbox required checked={f.consent_terms} onChange={(e) => setF({ ...f, consent_terms: e.target.checked })}
          label={<>I agree to the <Link className="text-brand-600 underline" to="/legal/terms" target="_blank">Terms</Link> and <Link className="text-brand-600 underline" to="/legal/privacy" target="_blank">Privacy Policy</Link>.</>} />
        <Checkbox checked={f.consent_marketing} onChange={(e) => setF({ ...f, consent_marketing: e.target.checked })} label="Send me study tips and offers (optional)." />
        <Button type="submit" size="lg" loading={signup.isPending} className="w-full">Create account</Button>
      </form>
      <p className="mt-4 text-center text-sm text-slate-600">Already have an account? <Link to="/login" className="font-semibold text-brand-600">Log in</Link></p>
    </AuthShell>
  );
}

/** Phone OTP + email verification status (AUTH-02). */
export function VerifyAccount() {
  const { me, setMe } = useAuth();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const verify = useAction(() => api.post<Me>("/auth/phone/verify/", { code }));
  const resendSms = useAction(() => api.post("/auth/phone/send/"));
  const resendEmail = useAction(() => api.post("/auth/verify-email/resend/"));
  if (!me) return <Loading />;
  const done = me.is_verified;
  return (
    <AuthShell title="Verify your account" subtitle="We verify every parent and tutor before any booking or application.">
      <div className="space-y-6">
        <section>
          <h2 className="font-semibold">1. Phone number {me.phone_verified_at && <span className="text-brand-600">✓</span>}</h2>
          {!me.phone_verified_at ? (
            <form className="mt-2 space-y-3" onSubmit={(e) => { e.preventDefault(); verify.mutate(undefined, { onSuccess: (m) => setMe(m) }); }}>
              <p className="text-sm text-slate-600">Enter the 6-digit code we sent to {me.phone}.</p>
              <ErrorAlert error={verify.error} />
              <Input label="SMS code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} required value={code} onChange={(e) => setCode(e.target.value)} />
              <div className="flex gap-2">
                <Button type="submit" loading={verify.isPending}>Verify phone</Button>
                <Button type="button" variant="ghost" loading={resendSms.isPending} onClick={() => resendSms.mutate(undefined, { onSuccess: () => setMsg("A new code is on its way.") })}>Resend code</Button>
              </div>
            </form>
          ) : <p className="text-sm text-slate-600">Verified.</p>}
        </section>
        <section>
          <h2 className="font-semibold">2. Email address {me.email_verified_at && <span className="text-brand-600">✓</span>}</h2>
          {!me.email_verified_at ? (
            <div className="mt-2 space-y-2 text-sm text-slate-600">
              <p>We sent a link to <strong>{me.email}</strong>. Click it to verify, then come back here.</p>
              <Button type="button" variant="ghost" loading={resendEmail.isPending} onClick={() => resendEmail.mutate(undefined, { onSuccess: () => setMsg("Verification email sent.") })}>Resend email</Button>
            </div>
          ) : <p className="text-sm text-slate-600">Verified.</p>}
        </section>
        {msg && <Alert tone="green">{msg}</Alert>}
        <Button className="w-full" variant={done ? "primary" : "secondary"} onClick={() => nav(safeNext(params.get("next")) ?? homeFor(me))}>
          {done ? "Continue" : "I'll do this later"}
        </Button>
      </div>
    </AuthShell>
  );
}

export function VerifyEmail() {
  const [params] = useSearchParams();
  const { refresh } = useAuth();
  const [state, setState] = useState<"working" | "ok" | "error">("working");
  useEffect(() => {
    api.post("/auth/verify-email/", { uid: params.get("uid"), token: params.get("token") })
      .then(async () => { setState("ok"); await refresh(); })
      .catch(() => setState("error"));
  }, [params, refresh]);
  return (
    <AuthShell title="Email verification">
      {state === "working" && <Loading label="Verifying…" />}
      {state === "ok" && <Alert tone="green" title="Email verified">Thank you. <Link to="/verify" className="underline">Continue</Link></Alert>}
      {state === "error" && <Alert>This link is invalid or has expired. Log in and request a new one.</Alert>}
    </AuthShell>
  );
}

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const send = useAction(() => api.post("/auth/password/forgot/", { email }));
  return (
    <AuthShell title="Reset your password">
      {sent ? <Alert tone="green">If that email is registered, a reset link is on its way. It expires in 30 minutes.</Alert> : (
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); send.mutate(undefined, { onSuccess: () => setSent(true) }); }}>
          <ErrorAlert error={send.error} />
          <Input label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <Button type="submit" loading={send.isPending} className="w-full">Send reset link</Button>
        </form>
      )}
    </AuthShell>
  );
}

export function ResetPassword() {
  const [params] = useSearchParams();
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const reset = useAction(() => api.post("/auth/password/reset/", { uid: params.get("uid"), token: params.get("token"), password }));
  return (
    <AuthShell title="Choose a new password">
      {done ? <Alert tone="green">Password updated. <Link to="/login" className="underline">Log in</Link></Alert> : (
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); reset.mutate(undefined, { onSuccess: () => setDone(true) }); }}>
          {reset.error && !reset.error.field("password") && <ErrorAlert error={reset.error} />}
          <Input label="New password" type="password" minLength={10} required autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} error={reset.error?.field("password")} />
          <Button type="submit" loading={reset.isPending} className="w-full">Update password</Button>
        </form>
      )}
    </AuthShell>
  );
}

/** Staff are forced here until 2FA is set up and verified for the session (AUTH-06). */
export function TwoFactor() {
  const { me, setMe, logout } = useAuth();
  const nav = useNavigate();
  const [setup, setSetup] = useState<{ secret: string; qr_svg: string } | null>(null);
  const [code, setCode] = useState("");
  const needsSetup = !!me && !me.totp_enabled;
  useEffect(() => {
    if (needsSetup) api.get<{ secret: string; qr_svg: string }>("/auth/2fa/setup/").then(setSetup).catch(() => undefined);
  }, [needsSetup]);
  const submit = useAction(() => api.post<Me>(needsSetup ? "/auth/2fa/enable/" : "/auth/2fa/verify/", { code }));
  if (!me) return <Loading />;
  return (
    <AuthShell title={needsSetup ? "Set up two-factor authentication" : "Confirm it's you"}
      subtitle={needsSetup ? (me.is_staff_member ? "Two-factor authentication is required for all staff accounts." : "Add an extra layer of security to your account.") : "Enter the code from your authenticator app."}>
      {needsSetup && setup && (
        <div className="mb-4 space-y-2 text-sm text-slate-600">
          <p>Scan this QR code with Google Authenticator, Microsoft Authenticator or a similar app:</p>
          <div className="mx-auto w-48 rounded-lg bg-white p-2 ring-1 ring-slate-200 [&_svg]:h-auto [&_svg]:w-full" dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
          <p>Or enter this key manually: <code className="rounded bg-slate-100 px-1 break-all">{setup.secret}</code></p>
        </div>
      )}
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); submit.mutate(undefined, { onSuccess: (m) => { setMe(m); nav(homeFor(m)); } }); }}>
        <ErrorAlert error={submit.error} />
        <Input label="6-digit code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} required value={code} onChange={(e) => setCode(e.target.value)} />
        <Button type="submit" loading={submit.isPending} className="w-full">{needsSetup ? "Enable two-factor" : "Verify"}</Button>
      </form>
      <button className="mt-4 w-full text-center text-sm text-slate-500 hover:underline" onClick={async () => { await logout(); nav("/login"); }}>Log out</button>
    </AuthShell>
  );
}
