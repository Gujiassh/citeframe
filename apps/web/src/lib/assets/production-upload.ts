export const PDF_UPLOAD_MIME_TYPE = "application/pdf";
export const IMAGE_UPLOAD_MIME_TYPES = [
  "image/png",
  "image/jpeg",
  "image/webp",
] as const;
export const PRODUCTION_UPLOAD_MIME_TYPES = [
  PDF_UPLOAD_MIME_TYPE,
  ...IMAGE_UPLOAD_MIME_TYPES,
] as const;

const MIME_TYPE_BY_EXTENSION: Readonly<Record<string, typeof PRODUCTION_UPLOAD_MIME_TYPES[number]>> = {
  pdf: PDF_UPLOAD_MIME_TYPE,
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
};

export const PRODUCTION_UPLOAD_ACCEPT = [
  ...PRODUCTION_UPLOAD_MIME_TYPES,
  ...Object.keys(MIME_TYPE_BY_EXTENSION).map((extension) => `.${extension}`),
].join(",");

export type ProductionUploadDescriptor = {
  mimeType: typeof PRODUCTION_UPLOAD_MIME_TYPES[number];
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
