import type { Chat } from '../types';

export interface ChatGroup {
  label: string;
  chats: Chat[];
}

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

export function groupChatsByDate(chats: Chat[]): ChatGroup[] {
  const today = startOfDay(new Date());
  const yesterday = today - 86_400_000;
  const weekAgo = today - 7 * 86_400_000;

  const buckets: Record<string, Chat[]> = {
    Today: [],
    Yesterday: [],
    'Previous 7 days': [],
    Older: [],
  };

  for (const chat of [...chats].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))) {
    const t = startOfDay(new Date(chat.updatedAt));
    if (t >= today) buckets.Today.push(chat);
    else if (t >= yesterday) buckets.Yesterday.push(chat);
    else if (t >= weekAgo) buckets['Previous 7 days'].push(chat);
    else buckets.Older.push(chat);
  }

  return Object.entries(buckets)
    .filter(([, chats]) => chats.length > 0)
    .map(([label, chats]) => ({ label, chats }));
}
