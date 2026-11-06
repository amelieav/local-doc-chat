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

export interface Word {
  text: string;
  x0: number;
  top: number;
  x1: number;
  bottom: number;
}

export interface Citation {
  marker: number;
  document_id: string;
  filename: string;
  page_number: number;
  passage: string;
  words: Word[];
}

export interface Answer {
  text: string;
  citations: Citation[];
}
