import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

import type { Word } from "./types";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

const MAX_SCALE = 1.5;

interface Props {
  documentId: string;
  pageNumber: number;
  words: Word[];
}

interface Size {
  width: number;
  height: number;
  scale: number;
}

// shortcut: word boxes are drawn unrotated, so rotated pages highlight in the wrong place.
export function PdfViewer({ documentId, pageNumber, words }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<Size | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const state = { cancelled: false };
    const loading = pdfjs.getDocument(`/api/documents/${documentId}/pdf`);
    void (async () => {
      try {
        const pdf = await loading.promise;
        const page = await pdf.getPage(pageNumber);
        // shortcut: fits the width once per page; resizing the window needs a reselect.
        const available = (scrollRef.current?.clientWidth ?? 800) - 64;
        const scale = Math.min(MAX_SCALE, available / page.getViewport({ scale: 1 }).width);
        const viewport = page.getViewport({ scale });
        const canvas = canvasRef.current;
        const context = canvas?.getContext("2d");
        if (state.cancelled || !canvas || !context) {
          return;
        }
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        setSize({ width: viewport.width, height: viewport.height, scale });
        setError("");
        await page.render({ canvasContext: context, viewport }).promise;
      } catch (e) {
        if (!state.cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      }
    })();
    return () => {
      state.cancelled = true;
      void loading.destroy();
    };
  }, [documentId, pageNumber]);

  // Bring the highlighted passage into view, with some page above it for context.
  useEffect(() => {
    const first = words[0];
    if (size && first) {
      scrollRef.current?.scrollTo({ top: Math.max(0, first.top * size.scale - 120) });
    }
  }, [size, words]);

  return (
    <div className="viewer-scroll" ref={scrollRef}>
      {error && <p className="notice error">{error}</p>}
      <div className="page" style={{ width: size?.width, height: size?.height }}>
        <canvas ref={canvasRef} />
        {size &&
          words.map((w, i) => (
            <div
              key={i}
              className="highlight"
              style={{
                left: w.x0 * size.scale,
                top: w.top * size.scale,
                width: (w.x1 - w.x0) * size.scale,
                height: (w.bottom - w.top) * size.scale,
              }}
            />
          ))}
      </div>
    </div>
  );
}
