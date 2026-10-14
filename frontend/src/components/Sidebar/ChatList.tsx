import { useEffect, useRef, useState } from 'react';
import { MoreHorizontal, Pencil, Trash2 } from 'lucide-react';
import type { Chat } from '../../types';
import { groupChatsByDate } from '../../utils/groupChats';
import styles from './ChatList.module.css';

interface ChatListProps {
  chats: Chat[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
}

export function ChatList({ chats, activeId, onSelect, onRename, onDelete }: ChatListProps) {
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpenMenuId(null);
      }
    }
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  const groups = groupChatsByDate(chats);

  if (groups.length === 0) {
    return <div className={styles.emptyHistory}>No chats match your search.</div>;
  }

  function startRename(chat: Chat) {
    setRenamingId(chat.id);
    setDraftTitle(chat.title);
    setOpenMenuId(null);
  }

  function commitRename(id: string) {
    if (draftTitle.trim()) onRename(id, draftTitle.trim());
    setRenamingId(null);
  }

  return (
    <div ref={containerRef}>
      {groups.map((group) => (
        <div key={group.label}>
          <div className="group-label">{group.label}</div>
          {group.chats.map((chat) => (
            <div
              key={chat.id}
              className={`${styles.item} ${chat.id === activeId ? styles.active : ''}`}
              onClick={() => onSelect(chat.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && onSelect(chat.id)}
            >
              {renamingId === chat.id ? (
                <input
                  autoFocus
                  className={styles.renameInput}
                  value={draftTitle}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => setDraftTitle(e.target.value)}
                  onBlur={() => commitRename(chat.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') commitRename(chat.id);
                    if (e.key === 'Escape') setRenamingId(null);
                  }}
                />
              ) : (
                <span className={styles.title}>{chat.title}</span>
              )}

              <button
                className={`icon-btn ${styles.menuBtn} ${openMenuId === chat.id ? styles.open : ''}`}
                aria-label="More options"
                onClick={(e) => {
                  e.stopPropagation();
                  setOpenMenuId(openMenuId === chat.id ? null : chat.id);
                }}
              >
                <MoreHorizontal size={16} strokeWidth={1.5} />
              </button>

              {openMenuId === chat.id && (
                <div className={styles.menu} onClick={(e) => e.stopPropagation()}>
                  <button className={styles.menuItem} onClick={() => startRename(chat)}>
                    <Pencil size={14} strokeWidth={1.5} /> Rename
                  </button>
                  <button
                    className={`${styles.menuItem} ${styles.danger}`}
                    onClick={() => {
                      onDelete(chat.id);
                      setOpenMenuId(null);
                    }}
                  >
                    <Trash2 size={14} strokeWidth={1.5} /> Delete
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
