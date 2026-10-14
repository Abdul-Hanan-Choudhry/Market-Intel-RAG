import type { Chat, ThemeMode } from '../types';

const CHATS_KEY = 'market-intel.chats';
const ACTIVE_ID_KEY = 'market-intel.activeId';
const THEME_KEY = 'market-intel.theme';

export function loadChats(): Chat[] {
  try {
    const raw = localStorage.getItem(CHATS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveChats(chats: Chat[]) {
  try {
    localStorage.setItem(CHATS_KEY, JSON.stringify(chats));
  } catch {
    // storage full or unavailable - the UI still works for the current session
  }
}

export function loadActiveId(): string | null {
  try {
    return localStorage.getItem(ACTIVE_ID_KEY);
  } catch {
    return null;
  }
}

export function saveActiveId(id: string | null) {
  try {
    if (id) localStorage.setItem(ACTIVE_ID_KEY, id);
    else localStorage.removeItem(ACTIVE_ID_KEY);
  } catch {
    // ignore
  }
}

export function loadTheme(): ThemeMode {
  try {
    const raw = localStorage.getItem(THEME_KEY);
    return raw === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

export function saveTheme(theme: ThemeMode) {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // ignore
  }
}
