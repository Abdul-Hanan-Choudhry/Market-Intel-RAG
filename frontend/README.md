# Market Intel — Frontend

A minimal, typographic chat interface for the Enterprise RAG system, in the style of
Claude/ChatGPT/Gemini — calm, text-first, no dashboards or decoration. Built with
React + TypeScript + Vite, CSS Modules, and a small set of design tokens.

## Run it

```bash
cd frontend
npm install
npm run dev       # http://localhost:5173
```

It talks to the **real backend** by default: `src/services/api.ts` calls the FastAPI
`POST /ask/stream` SSE endpoint and the Settings → Knowledge base tab reads `GET /stats`,
so answers, citations, and document counts are all live and grounded in the actual index —
nothing in the running app is mocked. `src/data/mockData.ts` is kept only as example
content for offline component development; it is not used by the app anymore.

## Wiring up the real backend

Start `rag serve` (see the project root README) before `npm run dev` — the API must be
running at `http://127.0.0.1:8000` (its CORS config already allows `localhost:5173`). If
it isn't reachable, the chat and Knowledge base tab show an inline "Can't reach the API…"
message instead of failing silently.

```bash
# optional: point at a non-default API host
echo "VITE_API_URL=http://127.0.0.1:8000" > .env
```

## Structure

```
src/
  styles/tokens.css        colors, spacing, radius, type scale (light + dark via CSS vars)
  styles/global.css        resets, focus rings, a few shared utility classes
  types.ts                 Chat, ChatMessage, Source, Citation, UploadedFile
  data/mockData.ts         example chat history (unused at runtime, kept for reference)
  services/api.ts          streamAnswer() — calls the real POST /ask/stream SSE endpoint
  utils/groupChats.ts      Today / Yesterday / Previous 7 days / Older grouping
  components/
    Sidebar/                Sidebar, ChatList (search, history, rename/delete)
    Chat/                   ChatPanel (incl. Clear chat), ChatMessage, Composer, EmptyState
    CitationPanel/           right-side panel showing the highlighted source passage
    Settings/                SettingsModal (General, Appearance, Knowledge base — live /stats, Data & Privacy)
  App.tsx                   state + wiring (no routing library needed for one screen)
```

## Design notes

- All color/spacing/radius/type values live in `tokens.css` as CSS variables; dark mode is
  `[data-theme="dark"]` overriding the same variable names, toggled from Settings →
  Appearance.
- Assistant answers render in a serif face (Source Serif 4) for long-form reading, like
  Claude; UI chrome stays in Inter.
- Nothing in the chat screen shows model names, token counts or parameters — those only
  appear in Settings, per the brief.
- Icons are Lucide, 1.5px stroke, used only where functional (new chat, attach, send,
  copy, regenerate, collapse sidebar, more options, close).
