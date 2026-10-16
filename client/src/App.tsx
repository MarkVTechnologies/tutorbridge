import { lazy, Suspense, type ComponentType } from "react";
import { createBrowserRouter, Navigate, Outlet, RouterProvider, useRouteError } from "react-router-dom";

import { AppLayout, PublicLayout } from "@/components/Layout";
import { Alert, ButtonLink, Loading } from "@/components/ui";
import { RequireAuth } from "@/lib/auth";
import { Home, HowItWorks, Legal, Pricing, Safety, TeachWithUs } from "@/pages/public/Marketing";

// Everything except the home/marketing pages is split into its own chunk so first load stays light on slow networks (WEB-03).
function page<M extends Record<string, unknown>>(load: () => Promise<M>, name: keyof M) {
  const C = lazy(() => load().then((m) => ({ default: m[name] as ComponentType })));
  return (
    <Suspense fallback={<Loading />}>
      <C />
    </Suspense>
  );
}
const auth = () => import("@/pages/auth/Auth");
const content = () => import("@/pages/public/Content");
const tutorsPublic = () => import("@/pages/public/Tutors");
const shared = () => import("@/pages/shared/Shared");
const parent = () => import("@/pages/parent/Parent");
const tutor = () => import("@/pages/tutor/Tutor");
const onboarding = () => import("@/pages/tutor/Onboarding");
const vetting = () => import("@/pages/staff/Vetting");
const ops = () => import("@/pages/staff/Ops");
const finance = () => import("@/pages/staff/Finance");
const safety = () => import("@/pages/staff/Safety");
const admin = () => import("@/pages/staff/Admin");

function ErrorPage() {
  const err = useRouteError() as { status?: number; message?: string };
  return (
    <div className="mx-auto max-w-lg px-4 py-20 text-center">
      <h1 className="text-3xl font-bold">{err?.status === 404 ? "Page not found" : "Something went wrong"}</h1>
      {err?.status !== 404 && <div className="mt-4"><Alert>{err?.message ?? "Please refresh and try again."}</Alert></div>}
      <ButtonLink to="/" className="mt-6">Go home</ButtonLink>
    </div>
  );
}

const router = createBrowserRouter([
  {
    errorElement: <ErrorPage />,
    children: [
      {
        element: <PublicLayout />,
        children: [
          { path: "/", element: <Home /> },
          { path: "/how-it-works", element: <HowItWorks /> },
          { path: "/safety", element: <Safety /> },
          { path: "/pricing", element: <Pricing /> },
          { path: "/teach", element: <TeachWithUs /> },
          { path: "/faq", element: page(content, "Faq") },
          { path: "/contact", element: page(content, "Contact") },
          { path: "/blog", element: page(content, "Blog") },
          { path: "/blog/:slug", element: page(content, "BlogPost") },
          { path: "/legal/:page", element: <Legal /> },
          { path: "/tutors", element: page(tutorsPublic, "FindTutors") },
          { path: "/tutors/:id", element: page(tutorsPublic, "TutorProfile") },
          { path: "/home-tutors/:subject/:area", element: page(content, "SeoLanding") },
          { path: "/reference/:token", element: page(content, "ReferenceForm") },
          { path: "/payments/callback", element: page(shared, "PaymentCallback") },
          { path: "/dev/fake-checkout", element: page(shared, "FakeCheckout") },
        ],
      },
      { path: "/login", element: page(auth, "Login") },
      { path: "/signup", element: page(auth, "Signup") },
      { path: "/forgot-password", element: page(auth, "ForgotPassword") },
      { path: "/reset-password", element: page(auth, "ResetPassword") },
      { path: "/verify-email", element: page(auth, "VerifyEmail") },
      { path: "/verify", element: <RequireAuth>{page(auth, "VerifyAccount")}</RequireAuth> },
      { path: "/account/2fa", element: <RequireAuth>{page(auth, "TwoFactor")}</RequireAuth> },
      {
        element: <RequireAuth><AppLayout area="auto" /></RequireAuth>,
        children: [
          { path: "/account", element: page(shared, "Account") },
          { path: "/notifications", element: page(shared, "Notifications") },
          { path: "/messages", element: page(shared, "Messages") },
          { path: "/messages/:id", element: page(shared, "Messages") },
        ],
      },
      {
        path: "/parent",
        element: <RequireAuth roles={["parent"]}><AppLayout area="parent" /></RequireAuth>,
        children: [
          { index: true, element: page(parent, "ParentDashboard") },
          { path: "children", element: page(parent, "Children") },
          { path: "requests", element: page(parent, "Requests") },
          { path: "requests/new", element: page(parent, "NewRequest") },
          { path: "requests/:id", element: page(parent, "RequestDetail") },
          { path: "bookings", element: page(parent, "ParentBookings") },
          { path: "bookings/:id", element: page(parent, "ParentBookingDetail") },
          { path: "lessons/:id", element: <LessonRedirect /> },
          { path: "wallet", element: page(parent, "Wallet") },
        ],
      },
      {
        path: "/tutor",
        element: <RequireAuth roles={["tutor"]}><AppLayout area="tutor" /></RequireAuth>,
        children: [
          { index: true, element: page(tutor, "TutorDashboard") },
          { path: "onboarding", element: page(onboarding, "Onboarding") },
          { path: "invitations", element: page(tutor, "Invitations") },
          { path: "bookings", element: page(tutor, "TutorBookings") },
          { path: "bookings/:id", element: page(tutor, "TutorBookingDetail") },
          { path: "lessons", element: page(tutor, "TutorLessons") },
          { path: "lessons/:id", element: page(tutor, "LessonPage") },
          { path: "earnings", element: page(tutor, "TutorEarnings") },
        ],
      },
      {
        path: "/staff",
        element: <RequireAuth roles="staff"><AppLayout area="staff" /></RequireAuth>,
        children: [
          { index: true, element: page(vetting, "StaffDashboard") },
          { path: "vetting", element: page(vetting, "VettingQueue") },
          { path: "vetting/:id", element: page(vetting, "VettingDetail") },
          { path: "interviews", element: page(vetting, "Interviews") },
          { path: "questions", element: page(vetting, "Questions") },
          { path: "requests", element: page(ops, "StaffRequests") },
          { path: "requests/:id", element: page(ops, "StaffRequestDetail") },
          { path: "bookings", element: page(ops, "StaffBookings") },
          { path: "bookings/:id", element: page(ops, "StaffBookingDetail") },
          { path: "finance", element: page(finance, "Finance") },
          { path: "payouts", element: page(finance, "Payouts") },
          { path: "payouts/:id", element: page(finance, "PayoutDetail") },
          { path: "disputes", element: page(safety, "Disputes") },
          { path: "incidents", element: page(safety, "Incidents") },
          { path: "incidents/:id", element: page(safety, "Incidents") },
          { path: "messages", element: page(safety, "FlaggedMessages") },
          { path: "reviews", element: page(safety, "Reviews") },
          { path: "users", element: page(admin, "Users") },
          { path: "users/:id", element: page(admin, "UserDetail") },
          { path: "settings", element: page(admin, "Settings") },
          { path: "team", element: page(admin, "StaffAccounts") },
          { path: "audit", element: page(admin, "AuditLog") },
        ],
      },
      { path: "*", element: <PublicLayout />, children: [{ path: "*", element: <NotFound /> }] },
    ],
  },
]);

/** Notification links point at a lesson; parents see lessons inside their booking page. */
function LessonRedirect() {
  return <Navigate to="/parent/bookings" replace />;
}

function NotFound() {
  return (
    <div className="mx-auto max-w-lg px-4 py-20 text-center">
      <h1 className="text-3xl font-bold">Page not found</h1>
      <ButtonLink to="/" className="mt-6">Go home</ButtonLink>
      <Outlet />
    </div>
  );
}

export default function App() {
  return <RouterProvider router={router} />;
}
