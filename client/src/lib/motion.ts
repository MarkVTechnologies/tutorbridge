/**
 * Motion, loaded lazily (WEB-03: fast on mid-range phones and slow networks).
 *
 * Components use the slim `m` component (re-exported as `motion`) and the animation
 * engine is fetched in a separate chunk after first paint via <LazyMotion>. Import
 * from here, never from "motion/react" directly, or the full library lands in the
 * main bundle again.
 */
export { AnimatePresence, LazyMotion, m as motion, type HTMLMotionProps } from "motion/react";

export const loadMotionFeatures = () => import("./motion-features").then((mod) => mod.default);
