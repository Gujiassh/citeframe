import { DocumentEvidenceRenderer } from "@/components/evidence/document-viewer";
import { AudioEvidenceRenderer } from "@/components/evidence/audio-viewer";
import { HtmlEvidenceRenderer } from "@/components/evidence/html-viewer";
import { ImageEvidenceRenderer } from "@/components/image-viewer";
import { PdfEvidenceRenderer } from "@/components/pdf-viewer";
import {
  DOCUMENT_UPLOAD_MIME_TYPE,
  IMAGE_UPLOAD_MIME_TYPES,
  PDF_UPLOAD_MIME_TYPE,
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
    assetKind: "html",
    locatorKinds: ["html_anchor"],
    label: "HTML",
    uploadAccept: [],
    EvidenceRenderer: HtmlEvidenceRenderer,
  },
  {
    assetKind: "audio",
    locatorKinds: ["audio_range"],
    label: "Audio",
    uploadAccept: [],
    EvidenceRenderer: AudioEvidenceRenderer,
  },
]);
