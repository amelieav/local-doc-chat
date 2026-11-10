import { useCallback, useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";

import { api } from "./api";
import { PdfViewer } from "./PdfViewer";
import type { Answer, Citation, DocumentInfo, UploadResult } from "./types";

interface Turn {
  id: number;
  question: string;
  answer?: Answer;
  error?: string;
}

interface Viewing {
  key: string;
  citation: Citation;
}

/** Turns "[1]" in the answer text into buttons that open that source. */
function AnswerText({
  turnId,
  answer,
  activeKey,
  onOpen,
}: {
  turnId: number;
  answer: Answer;
  activeKey: string | undefined;
  onOpen: (viewing: Viewing) => void;
}) {
  const parts = answer.text.split(/\[(\d+)\]/);
  return (
    <p className={answer.citations.length === 0 ? "answer dont-know" : "answer"}>
      {parts.map((part, i) => {
        if (i % 2 === 0) {
          return part;
        }
        const citation = answer.citations.find((c) => c.marker === Number(part));
        if (!citation) {
          return `[${part}]`;
        }
        const key = `${String(turnId)}-${part}`;
        return (
          <button
            key={i}
            className={key === activeKey ? "marker active" : "marker"}
            onClick={() => {
              onOpen({ key, citation });
            }}
          >
            {part}
          </button>
        );
      })}
    </p>
  );
}

export function App() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [viewing, setViewing] = useState<Viewing | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const nextId = useRef(1);
  const threadEnd = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    threadEnd.current?.scrollIntoView({ block: "end" });
  }, [turns]);

  const onFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }
    void run(`Reading ${file.name}. This can take a while...`, async () => {
      const result = await api<UploadResult>(
        `/documents?filename=${encodeURIComponent(file.name)}`,
        { method: "POST", headers: { "Content-Type": "application/pdf" }, body: file },
      );
      if (!result.created) {
        setError(`${file.name} was already added.`);
      }
      await refresh();
    });
  };

  const onDelete = (doc: DocumentInfo) => {
    void run(`Removing ${doc.filename}...`, async () => {
      await api(`/documents/${doc.id}`, { method: "DELETE" });
      if (viewing?.citation.document_id === doc.id) {
        setViewing(null);
      }
      await refresh();
    });
  };

  const pending = turns.some((t) => t.answer === undefined && t.error === undefined);

  const onAsk = (event: FormEvent) => {
    event.preventDefault();
    const text = question.trim();
    if (text === "" || pending) {
      return;
    }
    const id = nextId.current++;
    setQuestion("");
    setTurns((all) => [...all, { id, question: text }]);
    const settle = (patch: Partial<Turn>) => {
      setTurns((all) => all.map((t) => (t.id === id ? { ...t, ...patch } : t)));
    };
    api<Answer>("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text }),
    }).then(
      (answer) => {
        settle({ answer });
      },
      (e: unknown) => {
        settle({ error: e instanceof Error ? e.message : String(e) });
      },
    );
  };

  const busy = status !== "";

  return (
    <div className="app">
      <header className="masthead">
        <h1>Chat with your PDFs</h1>
      </header>

      <section className="pane side">
        <div className="library">
          <h2 className="section-title">Documents</h2>
          {documents.length === 0 ? (
            <p className="empty">Nothing here yet.</p>
          ) : (
            <ul className="doc-list">
              {documents.map((doc) => (
                <li key={doc.id}>
                  <span className="doc-name" title={doc.filename}>
                    {doc.filename}
                  </span>
                  <span className="doc-meta">
                    {doc.page_count} p{doc.status === "no_text" ? ", no text" : ""}
                  </span>
                  <button
                    className="link-button"
                    disabled={busy}
                    onClick={() => {
                      onDelete(doc);
                    }}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
          <label className="upload">
            Add a PDF
            <input type="file" accept="application/pdf" disabled={busy} onChange={onFile} />
          </label>
          {busy && <p className="notice">{status}</p>}
          {error && <p className="notice error">{error}</p>}
        </div>

        <div className="thread">
          {turns.length === 0 && <p className="empty">Add a PDF, then ask a question about it.</p>}
          {turns.map((turn) => (
            <div className="turn" key={turn.id}>
              <p className="question">{turn.question}</p>
              {turn.answer ? (
                <>
                  <AnswerText
                    turnId={turn.id}
                    answer={turn.answer}
                    activeKey={viewing?.key}
                    onOpen={setViewing}
                  />
                  <ul className="sources">
                    {turn.answer.citations.map((c) => {
                      const key = `${String(turn.id)}-${String(c.marker)}`;
                      return (
                        <li key={c.marker}>
                          <button
                            className={key === viewing?.key ? "source active" : "source"}
                            onClick={() => {
                              setViewing({ key, citation: c });
                            }}
                          >
                            <span className="source-name">
                              {c.marker}. {c.filename}, page {c.page_number}
                            </span>
                            <span className="source-text">{c.passage}</span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </>
              ) : turn.error ? (
                <p className="notice error">{turn.error}</p>
              ) : (
                <p className="answer pending">Reading your documents...</p>
              )}
            </div>
          ))}
          <div ref={threadEnd} />
        </div>

        <form className="composer" onSubmit={onAsk}>
          <input
            value={question}
            onChange={(e) => {
              setQuestion(e.target.value);
            }}
            placeholder="Ask about your documents"
            aria-label="Question"
          />
          <button disabled={pending || question.trim() === ""}>Ask</button>
        </form>
      </section>

      <section className="pane viewer">
        {viewing ? (
          <>
            <div className="viewer-bar">
              <h2>
                {viewing.citation.filename}, page {viewing.citation.page_number}
              </h2>
              <button
                className="link-button"
                onClick={() => {
                  setViewing(null);
                }}
              >
                Close
              </button>
            </div>
            <PdfViewer
              documentId={viewing.citation.document_id}
              pageNumber={viewing.citation.page_number}
              words={viewing.citation.words}
            />
          </>
        ) : (
          <p className="viewer-empty">Pick a source under an answer to see it in the PDF.</p>
        )}
      </section>
    </div>
  );
}
