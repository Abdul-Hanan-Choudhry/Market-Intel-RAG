import { useEffect, useRef, useState } from 'react';
import { Search, SquarePen } from 'lucide-react';
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
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userRowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (userRowRef.current && !userRowRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

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

      <div className={styles.userRow} ref={userRowRef}>
        <button
          style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flex: 1 }}
          onClick={() => setUserMenuOpen((v) => !v)}
          aria-haspopup="menu"
          aria-expanded={userMenuOpen}
        >
          <span className={styles.avatar}>AH</span>
          <span className={styles.userName}>Abdul Hanan</span>
        </button>

        {userMenuOpen && (
          <div className={styles.userMenu} role="menu">
            <button
              className={styles.userMenuItem}
              role="menuitem"
              onClick={() => {
                onOpenSettings();
                setUserMenuOpen(false);
              }}
            >
              Settings
            </button>
            <button className={styles.userMenuItem} role="menuitem">
              Log out
            </button>
          </div>
        )}
      </div>
      </aside>
    </>
  );
}
