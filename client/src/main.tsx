import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HeadProvider } from "react-head";
import { Slide, ToastContainer } from "react-toastify";
import "react-toastify/dist/ReactToastify.css";

import App from "./App";
import { ApiError } from "./lib/api";
import { AuthProvider } from "./lib/auth";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: true,
      // Don't retry client errors (403/404 etc.); retry flaky network once — mid-range phones on slow networks.
      retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 1,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <HeadProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <App />
          <ToastContainer position="bottom-right" transition={Slide} autoClose={3500} hideProgressBar newestOnTop closeOnClick pauseOnFocusLoss={false} theme="light" />
        </AuthProvider>
      </QueryClientProvider>
    </HeadProvider>
  </StrictMode>,
);

// WEB-04: installable PWA with an offline shell for the lesson page.
if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => undefined));
}
