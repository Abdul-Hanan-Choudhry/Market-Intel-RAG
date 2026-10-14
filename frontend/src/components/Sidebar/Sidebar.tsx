import { useState } from 'react';
import { Search, Settings, SquarePen } from 'lucide-react';
import type { Chat } from '../../types';
import { ChatList } from './ChatList';
import styles from './Sidebar.module.css';

interface SidebarProps {
  chats: Chat[];
  activeId: string | null;
  collapsed: boolean;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onOpenSettings: () => void;
  onCollapse: () => void;
}

export function Sidebar({
  chats,
  activeId,
  collapsed,
  onSelect,
  onNewChat,
  onRename,
  onDelete,
  onOpenSettings,
  onCollapse,
}: SidebarProps) {
  const [query, setQuery] = useState('');

  const filtered = query.trim()
    ? chats.filter((c) => c.title.toLowerCase().includes(query.trim().toLowerCase()))
    : chats;

  return (
    <>
      {!collapsed && <div className={styles.overlay} onClick={onCollapse} />}
      <aside className={`${styles.sidebar} ${collapsed ? styles.collapsed : ''}`} aria-hidden={collapsed}>
      <div className={styles.topRow}>
        <span className={styles.productName}>Market Intel</span>
      </div>

      <button className={styles.newChatBtn} onClick={onNewChat}>
        <SquarePen size={16} strokeWidth={1.5} />
        New chat
      </button>

      <div className={styles.searchWrap}>
        <Search size={15} strokeWidth={1.5} />
        <input
          className={styles.searchInput}
          placeholder="Search chats"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search chats"
        />
      </div>

      <nav className={`${styles.history} scroll-thin`} aria-label="Chat history">
        <ChatList
          chats={filtered}
          activeId={activeId}
          onSelect={onSelect}
          onRename={onRename}
          onDelete={onDelete}
        />
      </nav>

      <button className={styles.settingsRow} onClick={onOpenSettings}>
        <Settings size={16} strokeWidth={1.5} />
        Settings
      </button>
    </aside>
    </>
  );
}
