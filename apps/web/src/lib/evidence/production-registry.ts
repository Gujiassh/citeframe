import { DocumentEvidenceRenderer } from "@/components/evidence/document-viewer";
import { AudioEvidenceRenderer } from "@/components/evidence/audio-viewer";
import { VideoEvidenceRenderer } from "@/components/evidence/video-viewer";
import { HtmlEvidenceRenderer } from "@/components/evidence/html-viewer";
import {
  DocxEvidenceRenderer,
  PptxEvidenceRenderer,
  XlsxEvidenceRenderer,
} from "@/components/evidence/office-viewer";
import { ImageEvidenceRenderer } from "@/components/image-viewer";
import { PdfEvidenceRenderer } from "@/components/pdf-viewer";
import {
  AUDIO_UPLOAD_MIME_TYPES,
  DOCUMENT_UPLOAD_MIME_TYPE,
  DOCX_UPLOAD_MIME_TYPE,
  HTML_UPLOAD_MIME_TYPE,
  IMAGE_UPLOAD_MIME_TYPES,
  PDF_UPLOAD_MIME_TYPE,
  PPTX_UPLOAD_MIME_TYPE,
  VIDEO_UPLOAD_MIME_TYPES,
  XLSX_UPLOAD_MIME_TYPE,
} from "@/lib/assets/production-upload";
import { createEvidenceModuleRegistry } from "./registry";

export const productionEvidenceRegistry = createEvidenceModuleRegistry([
  {
    assetKind: "pdf",
    locatorKinds: ["pdf_page", "pdf_region"],
    label: "PDF",
    uploadAccept: [PDF_UPLOAD_MIME_TYPE],
    EvidenceRenderer: PdfEvidenceRenderer,
  },
  {
    assetKind: "image",
    locatorKinds: ["image_region"],
    label: "Image",
    uploadAccept: IMAGE_UPLOAD_MIME_TYPES,
    EvidenceRenderer: ImageEvidenceRenderer,
  },
  {
    assetKind: "document",
    locatorKinds: ["document_anchor"],
    label: "Document",
    uploadAccept: [DOCUMENT_UPLOAD_MIME_TYPE],
    EvidenceRenderer: DocumentEvidenceRenderer,
  },
  {
    assetKind: "docx",
    locatorKinds: ["docx_anchor"],
    label: "DOCX",
    uploadAccept: [DOCX_UPLOAD_MIME_TYPE],
    EvidenceRenderer: DocxEvidenceRenderer,
  },
  {
    assetKind: "xlsx",
    locatorKinds: ["xlsx_range"],
    label: "XLSX",
    uploadAccept: [XLSX_UPLOAD_MIME_TYPE],
    EvidenceRenderer: XlsxEvidenceRenderer,
  },
  {
    assetKind: "pptx",
    locatorKinds: ["pptx_shape"],
    label: "PPTX",
    uploadAccept: [PPTX_UPLOAD_MIME_TYPE],
    EvidenceRenderer: PptxEvidenceRenderer,
  },
  {
    assetKind: "html",
    locatorKinds: ["html_anchor"],
    label: "HTML",
    uploadAccept: [HTML_UPLOAD_MIME_TYPE],
    EvidenceRenderer: HtmlEvidenceRenderer,
  },
  {
    assetKind: "audio",
    locatorKinds: ["audio_range"],
    label: "Audio",
    uploadAccept: [...AUDIO_UPLOAD_MIME_TYPES],
    EvidenceRenderer: AudioEvidenceRenderer,
  },
  {
    assetKind: "video",
    locatorKinds: ["video_range", "video_frame"],
    label: "Video",
    uploadAccept: [...VIDEO_UPLOAD_MIME_TYPES],
    EvidenceRenderer: VideoEvidenceRenderer,
  },
]);
