import { useCallback, useEffect, useState, type ChangeEvent, type FormEvent } from "react";

import { api } from "./api";
import { PdfViewer } from "./PdfViewer";
import type { Answer, Citation, DocumentInfo, UploadResult } from "./types";

export function App() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [viewing, setViewing] = useState<Citation | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const run = useCallback(async (label: string, task: () => Promise<void>) => {
    setStatus(label);
    setError("");
    try {
      await task();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStatus("");
    }
  }, []);

  const refresh = useCallback(async () => {
    setDocuments(await api<DocumentInfo[]>("/documents"));
  }, []);

  useEffect(() => {
    void run("Loading...", refresh);
  }, [run, refresh]);

  const onFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }
    void run(`Uploading and indexing ${file.name} (can take a while)...`, async () => {
      const result = await api<UploadResult>(
        `/documents?filename=${encodeURIComponent(file.name)}`,
        { method: "POST", headers: { "Content-Type": "application/pdf" }, body: file },
      );
      if (!result.created) {
        setError(`${file.name} was already uploaded.`);
      }
      await refresh();
    });
  };

  const onDelete = (doc: DocumentInfo) => {
    void run(`Deleting ${doc.filename}...`, async () => {
      await api(`/documents/${doc.id}`, { method: "DELETE" });
      await refresh();
    });
  };

  const onAsk = (event: FormEvent) => {
    event.preventDefault();
    void run("Thinking (local model, can take a while)...", async () => {
      setAnswer(null);
      setViewing(null);
      setAnswer(
        await api<Answer>("/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question }),
        }),
      );
    });
  };

  const busy = status !== "";

  return (
    <main style={{ maxWidth: 720, margin: "2rem auto", fontFamily: "sans-serif" }}>
      <h1>Local Doc Chat</h1>
      {busy && <p>{status}</p>}
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      <h2>Documents</h2>
      <input type="file" accept="application/pdf" disabled={busy} onChange={onFile} />
      <ul>
        {documents.map((doc) => (
          <li key={doc.id}>
            {doc.filename} ({doc.page_count} pages
            {doc.status === "no_text" ? ", no text found" : ""}){" "}
            <button
              disabled={busy}
              onClick={() => {
                onDelete(doc);
              }}
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
      {documents.length === 0 && <p>No documents yet.</p>}

      <h2>Ask</h2>
      <form onSubmit={onAsk}>
        <input
          value={question}
          onChange={(e) => {
            setQuestion(e.target.value);
          }}
          placeholder="Ask about your documents"
          style={{ width: "70%" }}
        />{" "}
        <button disabled={busy || question.trim() === ""}>Ask</button>
      </form>

      {answer && (
        <section>
          <p>{answer.text}</p>
          {answer.citations.map((c) => (
            <blockquote key={c.marker}>
              <button
                onClick={() => {
                  setViewing(c);
                }}
              >
                [{c.marker}] {c.filename}, page {c.page_number}
              </button>
              <br />
              <small>{c.passage}</small>
            </blockquote>
          ))}
        </section>
      )}

      {viewing && (
        <section>
          <h2>
            {viewing.filename}, page {viewing.page_number}{" "}
            <button
              onClick={() => {
                setViewing(null);
              }}
            >
              Close
            </button>
          </h2>
          <PdfViewer
            documentId={viewing.document_id}
            pageNumber={viewing.page_number}
            words={viewing.words}
          />
        </section>
      )}
    </main>
  );
}
