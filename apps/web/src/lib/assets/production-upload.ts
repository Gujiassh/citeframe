export const PDF_UPLOAD_MIME_TYPE = "application/pdf";
export const DOCUMENT_UPLOAD_MIME_TYPE = "text/markdown";
export const HTML_UPLOAD_MIME_TYPE = "text/html";
export const DOCX_UPLOAD_MIME_TYPE =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
export const XLSX_UPLOAD_MIME_TYPE =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
export const PPTX_UPLOAD_MIME_TYPE =
  "application/vnd.openxmlformats-officedocument.presentationml.presentation";
export const IMAGE_UPLOAD_MIME_TYPES = [
  "image/png",
  "image/jpeg",
  "image/webp",
] as const;
export const AUDIO_UPLOAD_MIME_TYPES = [
  "audio/mpeg",
  "audio/wav",
  "audio/mp4",
  "audio/webm",
] as const;
export const VIDEO_UPLOAD_MIME_TYPES = [
  "video/mp4",
  "video/webm",
] as const;

export const PRODUCTION_UPLOAD_MIME_TYPES = [
  PDF_UPLOAD_MIME_TYPE,
  ...IMAGE_UPLOAD_MIME_TYPES,
  DOCUMENT_UPLOAD_MIME_TYPE,
  HTML_UPLOAD_MIME_TYPE,
  DOCX_UPLOAD_MIME_TYPE,
  XLSX_UPLOAD_MIME_TYPE,
  PPTX_UPLOAD_MIME_TYPE,
  ...AUDIO_UPLOAD_MIME_TYPES,
  ...VIDEO_UPLOAD_MIME_TYPES,
] as const;

const MIME_TYPE_BY_EXTENSION: Readonly<Record<string, (typeof PRODUCTION_UPLOAD_MIME_TYPES)[number]>> = {
  pdf: PDF_UPLOAD_MIME_TYPE,
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
  md: DOCUMENT_UPLOAD_MIME_TYPE,
  markdown: DOCUMENT_UPLOAD_MIME_TYPE,
  html: HTML_UPLOAD_MIME_TYPE,
  htm: HTML_UPLOAD_MIME_TYPE,
  docx: DOCX_UPLOAD_MIME_TYPE,
  xlsx: XLSX_UPLOAD_MIME_TYPE,
  pptx: PPTX_UPLOAD_MIME_TYPE,
  mp3: "audio/mpeg",
  wav: "audio/wav",
  m4a: "audio/mp4",
  weba: "audio/webm",
  mp4: "video/mp4",
  webm: "video/webm",
};

export const PRODUCTION_UPLOAD_ACCEPT = [
  ...PRODUCTION_UPLOAD_MIME_TYPES,
  ...Object.keys(MIME_TYPE_BY_EXTENSION).map((extension) => `.${extension}`),
].join(",");

export type ProductionUploadDescriptor = {
  mimeType: (typeof PRODUCTION_UPLOAD_MIME_TYPES)[number];
};

export function getProductionUploadDescriptor(
  file: Pick<File, "name" | "type">,
): ProductionUploadDescriptor | null {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  const extensionMimeType = MIME_TYPE_BY_EXTENSION[extension];
  const declaredMimeType = file.type.trim().toLowerCase();
  const mimeType = PRODUCTION_UPLOAD_MIME_TYPES.find((candidate) => candidate === declaredMimeType);

  if (!mimeType || (extensionMimeType && extensionMimeType !== mimeType)) {
    return null;
  }

  return { mimeType };
}
