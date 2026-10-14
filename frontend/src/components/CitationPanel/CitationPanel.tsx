import { useEffect } from 'react';
import { X } from 'lucide-react';
import type { Source } from '../../types';
import styles from './CitationPanel.module.css';

interface CitationPanelProps {
  source: Source | null;
  onClose: () => void;
}

export function CitationPanel({ source, onClose }: CitationPanelProps) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!source) return null;

  const hasHighlight = source.matchStart != null && source.matchEnd != null && source.matchEnd > source.matchStart;
  const before = hasHighlight ? source.passage.slice(0, source.matchStart) : source.passage;
  const match = hasHighlight ? source.passage.slice(source.matchStart, source.matchEnd) : '';
  const after = hasHighlight ? source.passage.slice(source.matchEnd) : '';

  return (
    <>
      <div className={styles.overlay} onClick={onClose} />
      <aside className={styles.panel} role="complementary" aria-label="Source passage">
        <div className={styles.header}>
          <div className={styles.titleBlock}>
            <p className={styles.docTitle}>{source.title}</p>
            <p className={styles.meta}>
              {source.publisher}
              {source.section ? ` · ${source.section}` : ''}
              {source.date ? ` · ${source.date}` : ''}
            </p>
          </div>
          <button className="icon-btn" aria-label="Close" onClick={onClose}>
            <X size={18} strokeWidth={1.5} />
          </button>
        </div>
        <div className={`${styles.body} scroll-thin`}>
          <p className={styles.passage}>
            {before}
            <mark className={styles.highlight}>{match}</mark>
            {after}
          </p>
        </div>
      </aside>
    </>
  );
}
