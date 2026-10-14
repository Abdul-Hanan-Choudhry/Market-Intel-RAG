import { Fragment, useState } from 'react';
import { Copy, RotateCcw } from 'lucide-react';
import type { ChatMessage as ChatMessageType, Source } from '../../types';
import styles from './ChatMessage.module.css';

interface ChatMessageProps {
  message: ChatMessageType;
  isStreaming?: boolean;
  onCiteClick: (source: Source) => void;
  onRegenerate?: () => void;
}

/** Splits "text [1] more text [2][3]" into plain strings and citation markers. */
function renderWithCitations(
  content: string,
  message: ChatMessageType,
  onCiteClick: (source: Source) => void,
) {
  const parts = content.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (!match) return <Fragment key={i}>{part}</Fragment>;

    const n = Number(match[1]);
    const citation = message.citations?.find((c) => c.n === n);
    const source = message.sources?.find((s) => s.id === citation?.sourceId);
    if (!source) return <Fragment key={i}>{part}</Fragment>;

    return (
      <button key={i} className={styles.citeMarker} onClick={() => onCiteClick(source)}>
        {n}
      </button>
    );
  });
}

export function ChatMessage({ message, isStreaming, onCiteClick, onRegenerate }: ChatMessageProps) {
  const [sourcesOpen, setSourcesOpen] = useState(false);

  if (message.role === 'user') {
    return (
      <div className={`${styles.row} ${styles.user}`}>
        <div className={styles.bubble}>{message.content}</div>
      </div>
    );
  }

  return (
    <div className={styles.row}>
      <div style={{ width: '100%' }}>
        <div className={styles.assistant}>
          {renderWithCitations(message.content, message, onCiteClick)}
          {isStreaming && <span className={styles.caret} />}
        </div>

        {!isStreaming && message.sources && message.sources.length > 0 && (
          <div className={styles.footer}>
            <button className={styles.sourcesToggle} onClick={() => setSourcesOpen((v) => !v)}>
              Sources ({message.sources.length})
            </button>
            {sourcesOpen && (
              <div className={styles.sourcesList}>
                {message.sources.map((s) => (
                  <button key={s.id} className={styles.sourceRow} onClick={() => onCiteClick(s)}>
                    {s.title}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {!isStreaming && (
          <div className={styles.actions}>
            <button
              className="icon-btn"
              aria-label="Copy"
              onClick={() => navigator.clipboard.writeText(message.content)}
            >
              <Copy size={15} strokeWidth={1.5} />
            </button>
            <button className="icon-btn" aria-label="Regenerate" onClick={onRegenerate}>
              <RotateCcw size={15} strokeWidth={1.5} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
