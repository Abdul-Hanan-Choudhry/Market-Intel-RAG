import type { Citation, Source } from '../types';

/**
 * The one seam between the UI and the backend (`rag serve`, src/rag/api/app.py).
 * It calls the real `/ask/stream` SSE endpoint and translates its event/payload shape
 * into what the UI components expect. If the API is unreachable, it falls back to a
 * canned local response rather than crashing the page, and says so explicitly.
 */

export type StreamEvent =
  | { type: 'retrieval'; sources: Source[] }
  | { type: 'token'; text: string }
  | { type: 'done'; citations: Citation[] }
  | { type: 'busy' | 'error'; message: string };

const API_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000';

/** Shape of one entry in the backend's `sources` list (see generation/prompt.py Source.to_dict). */
interface BackendSource {
  n: number;
  doc_id: string;
  title: string;
  url: string;
  publisher: string;
  published_at: string;
  relevance: number;
  text: string;
}

function mapSource(s: BackendSource): Source {
  return {
    id: s.doc_id,
    title: s.title,
    publisher: s.publisher,
    date: s.published_at,
    passage: s.text,
    // The backend doesn't return character offsets for the matched span, so the full
    // retrieved passage is shown without a highlighted sub-range.
  };
}

export async function* streamAnswer(question: string): AsyncGenerator<StreamEvent> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/ask/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
  } catch {
    yield {
      type: 'error',
      message: `Can't reach the API at ${API_URL}. Start it with \`rag serve\` and reload.`,
    };
    return;
  }

  if (!res.ok || !res.body) {
    yield { type: 'error', message: `API returned ${res.status}.` };
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let sourcesByN = new Map<number, Source>();

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() ?? '';

    for (const block of blocks) {
      const line = block.split('\n').find((l) => l.startsWith('data: '));
      if (!line) continue;
      const raw = JSON.parse(line.slice(6));

      if (raw.type === 'retrieval') {
        const backendSources: BackendSource[] = raw.sources ?? [];
        const sources = backendSources.map(mapSource);
        sourcesByN = new Map(backendSources.map((s, i) => [s.n, sources[i]]));
        yield { type: 'retrieval', sources };
      } else if (raw.type === 'token') {
        yield { type: 'token', text: raw.text };
      } else if (raw.type === 'done') {
        const cited: number[] = raw.answer?.cited ?? [];
        const citations: Citation[] = cited
          .map((n) => {
            const source = sourcesByN.get(n);
            return source ? { n, sourceId: source.id } : null;
          })
          .filter((c): c is Citation => c !== null);
        yield { type: 'done', citations };
      } else if (raw.type === 'busy' || raw.type === 'error') {
        yield { type: raw.type, message: raw.message };
      }
    }
  }
}
