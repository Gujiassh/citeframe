"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function ResearchReportMarkdown({ content }: { content: string }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{content}</ReactMarkdown>;
}
