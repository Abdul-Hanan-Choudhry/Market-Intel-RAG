import { useEffect, useRef } from 'react';
import { Eraser, PanelLeft } from 'lucide-react';
import type { Chat, Source } from '../../types';
import { ChatMessage } from './ChatMessage';
import { Composer } from './Composer';
import { EmptyState } from './EmptyState';
import styles from './ChatPanel.module.css';

interface ChatPanelProps {
  chat: Chat | null;
  onToggleSidebar: () => void;
  onSend: (text: string) => void;
  onCiteClick: (source: Source) => void;
  onClearChat: () => void;
  isSearching: boolean;
  isStreaming: boolean;
}

export function ChatPanel({
  chat,
  onToggleSidebar,
  onSend,
  onCiteClick,
  onClearChat,
  isSearching,
  isStreaming,
}: ChatPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chat?.messages.length, isStreaming]);

  const hasMessages = !!chat && chat.messages.length > 0;

  return (
    <section className={styles.panel}>
      <div className={styles.topBar}>
        <button className="icon-btn" aria-label="Toggle sidebar" onClick={onToggleSidebar}>
          <PanelLeft size={18} strokeWidth={1.5} />
        </button>
        {hasMessages && (
          <button
            className="icon-btn"
            aria-label="Clear chat"
            title="Clear chat"
            onClick={onClearChat}
            style={{ marginLeft: 'auto' }}
          >
            <Eraser size={17} strokeWidth={1.5} />
          </button>
        )}
      </div>

      {hasMessages ? (
        <div className={`${styles.messages} scroll-thin`}>
          <div className={styles.messagesInner}>
            {chat.messages.map((m, i) => (
              <ChatMessage
                key={m.id}
                message={m}
                isStreaming={isStreaming && i === chat.messages.length - 1}
                onCiteClick={onCiteClick}
              />
            ))}
            {isSearching && <p className="searching-line">Searching documents…</p>}
            <div ref={bottomRef} />
          </div>
        </div>
      ) : (
        <EmptyState onPick={onSend} />
      )}

      <Composer onSend={onSend} disabled={isSearching || isStreaming} />
    </section>
  );
}
