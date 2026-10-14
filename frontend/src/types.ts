export type Role = 'user' | 'assistant';

export interface Source {
  id: string;
  title: string;
  publisher: string;
  section?: string;
  date?: string;
  passage: string;
  /** Substring of `passage` to highlight as the matching text. */
  matchStart: number;
  matchEnd: number;
}

export interface Citation {
  /** The inline marker number shown in the message text, e.g. 1 for "[1]". */
  n: number;
  sourceId: string;
}

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  citations?: Citation[];
  sources?: Source[];
  createdAt: string;
}

export interface Chat {
  id: string;
  title: string;
  updatedAt: string;
  messages: ChatMessage[];
}

export interface UploadedFile {
  id: string;
  name: string;
  status: 'processing' | 'ready';
}

export type ThemeMode = 'light' | 'dark';
