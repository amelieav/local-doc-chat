import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

import type { Word } from "./types";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

const SCALE = 1.4;

interface Props {
  documentId: string;
  pageNumber: number;
  words: Word[];
}

interface Size {
  width: number;
  height: number;
}

// shortcut: word boxes are drawn unrotated, so rotated pages highlight in the wrong place.
export function PdfViewer({ documentId, pageNumber, words }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState<Size | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const state = { cancelled: false };
    const loading = pdfjs.getDocument(`/api/documents/${documentId}/pdf`);
    void (async () => {
      try {
        const pdf = await loading.promise;
        const page = await pdf.getPage(pageNumber);
        const viewport = page.getViewport({ scale: SCALE });
        const canvas = canvasRef.current;
        const context = canvas?.getContext("2d");
        if (state.cancelled || !canvas || !context) {
          return;
        }
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        setSize({ width: viewport.width, height: viewport.height });
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

  return (
    <div>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      <div style={{ position: "relative", width: size?.width, height: size?.height }}>
        <canvas ref={canvasRef} style={{ display: "block" }} />
        {size &&
          words.map((w, i) => (
            <div
              key={i}
              style={{
                position: "absolute",
                left: w.x0 * SCALE,
                top: w.top * SCALE,
                width: (w.x1 - w.x0) * SCALE,
                height: (w.bottom - w.top) * SCALE,
                background: "rgba(255, 213, 0, 0.4)",
                pointerEvents: "none",
              }}
            />
          ))}
      </div>
    </div>
  );
}
