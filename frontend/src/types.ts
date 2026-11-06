// Mirrors the backend's JSON. Only the fields the page uses.

export interface DocumentInfo {
  id: string;
  filename: string;
  page_count: number;
  status: "ready" | "no_text";
}

export interface UploadResult {
  document: DocumentInfo;
  created: boolean;
}

export interface Citation {
  marker: number;
  filename: string;
  page_number: number;
  passage: string;
}

export interface Answer {
  text: string;
  citations: Citation[];
}
