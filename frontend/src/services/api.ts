import type { ChatMessage, Citation, Source } from '../types';
import { mockSources } from '../data/mockData';

/**
 * This file is the single seam between the UI and the backend. Right now it simulates a
 * streamed answer with mock retrieval so the interface is fully reviewable on its own.
 * To connect the real FastAPI backend (`rag serve`, see src/rag/api/app.py), replace the
 * body of `streamAnswer` with the commented implementation below — the event shape
 * (`retrieval` / `token` / `done` / `busy` / `error`) already matches what `/ask/stream`
 * sends over SSE, so no other UI code needs to change.
 */

export type StreamEvent =
  | { type: 'retrieval'; sources: Source[] }
  | { type: 'token'; text: string }
  | { type: 'done'; citations: Citation[] }
  | { type: 'busy' | 'error'; message: string };

const MOCK_ANSWER =
  "Based on the indexed sources, the central estimate points to a modest deceleration in growth alongside firmer inflation over the coming year [1]. The underlying detail varies by publication, but the direction of travel — slower growth, stickier prices — is consistent across the sources retrieved [2].";

const MOCK_SOURCES = Object.values(mockSources).slice(0, 2);

export async function* streamAnswer(question: string): AsyncGenerator<StreamEvent> {
  void question;
  await delay(500);
  yield { type: 'retrieval', sources: MOCK_SOURCES };
  await delay(400);

  const words = MOCK_ANSWER.split(' ');
  for (const word of words) {
    await delay(35 + Math.random() * 35);
    yield { type: 'token', text: word + ' ' };
  }

  yield {
    type: 'done',
    citations: MOCK_SOURCES.map((s, i) => ({ n: i + 1, sourceId: s.id })),
  };
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/* ---------------------------------------------------------------------------------------
// Real backend implementation (uncomment once the API in src/rag/api/app.py is reachable):

const API_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000';

export async function* streamAnswer(question: string): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${API_URL}/ask/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  });
  if (!res.body) throw new Error('No response body');

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() ?? '';
    for (const block of blocks) {
      const line = block.split('\n').find((l) => l.startsWith('data: '));
      if (line) yield JSON.parse(line.slice(6));
    }
  }
}
--------------------------------------------------------------------------------------- */

export type { ChatMessage };
