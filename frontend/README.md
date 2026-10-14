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

It runs fully on **mock data** (`src/data/mockData.ts`, `src/services/api.ts`) so the UI
is reviewable without the Python backend running.

## Wiring up the real backend

Everything the UI needs from the backend goes through `src/services/api.ts`. Start
`rag serve` (see the project root README), then swap the mock `streamAnswer` for the real
implementation already written (commented) at the bottom of that file — it calls the
existing `POST /ask/stream` SSE endpoint, whose event shape (`retrieval` / `token` / `done`
/ `busy` / `error`) is what the UI already expects, so no component changes are needed.

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
  data/mockData.ts         mock chat history + source passages
  services/api.ts          streamAnswer() — the one seam to the real backend
  utils/groupChats.ts      Today / Yesterday / Previous 7 days / Older grouping
  components/
    Sidebar/                Sidebar, ChatList (search, history, rename/delete, user menu)
    Chat/                   ChatPanel, ChatMessage, Composer, EmptyState
    CitationPanel/           right-side panel showing the highlighted source passage
    Settings/                SettingsModal (General, Appearance, Knowledge base, Data & Privacy, Account)
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
