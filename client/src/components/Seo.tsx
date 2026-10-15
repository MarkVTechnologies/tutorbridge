import { Meta, Title } from "react-head";

/** Per-page <title> and description for search engines and link previews (WEB-02). */
export function Seo({ title, description }: { title: string; description?: string }) {
  const full = title.includes("TutorBridge") ? title : `${title} · TutorBridge`;
  return (
    <>
      <Title>{full}</Title>
      {description && <Meta name="description" content={description} />}
      <Meta property="og:title" content={full} />
      {description && <Meta property="og:description" content={description} />}
    </>
  );
}
