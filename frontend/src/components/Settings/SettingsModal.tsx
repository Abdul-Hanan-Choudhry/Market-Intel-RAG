import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import type { ThemeMode } from '../../types';
import styles from './SettingsModal.module.css';

type Tab = 'General' | 'Appearance' | 'Knowledge base' | 'Data & Privacy';
const TABS: Tab[] = ['General', 'Appearance', 'Knowledge base', 'Data & Privacy'];

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
  theme: ThemeMode;
  onThemeChange: (theme: ThemeMode) => void;
}

const API_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000';

interface KbStats {
  documents: number;
  chunks: number;
  sources: number;
  markets: Record<string, number>;
  newestDocument: string | null;
}

export function SettingsModal({ open, onClose, theme, onThemeChange }: SettingsModalProps) {
  const [tab, setTab] = useState<Tab>('General');
  const [kb, setKb] = useState<KbStats | 'loading' | 'error'>('loading');

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (!open || tab !== 'Knowledge base') return;
    setKb('loading');
    fetch(`${API_URL}/stats`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data) =>
        setKb({
          documents: data.pipeline.documents,
          chunks: data.pipeline.chunks,
          sources: data.sources,
          markets: data.markets,
          newestDocument: data.newest_document,
        }),
      )
      .catch(() => setKb('error'));
  }, [open, tab]);

  if (!open) return null;

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <nav className={styles.tabs}>
          <div className={styles.tabsHeading}>Settings</div>
          {TABS.map((t) => (
            <button
              key={t}
              className={`${styles.tab} ${tab === t ? styles.active : ''}`}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </nav>

        <div className={styles.content}>
          <button className={`icon-btn ${styles.closeBtn}`} aria-label="Close settings" onClick={onClose}>
            <X size={18} strokeWidth={1.5} />
          </button>

          {tab === 'General' && (
            <>
              <h2 className={styles.panelTitle}>General</h2>
              <div className={styles.row}>
                <div>
                  <div className={styles.rowLabel}>Response length</div>
                  <div className={styles.rowHint}>Shorter answers generate faster.</div>
                </div>
                <select className={styles.select} defaultValue="balanced">
                  <option value="concise">Concise</option>
                  <option value="balanced">Balanced</option>
                  <option value="detailed">Detailed</option>
                </select>
              </div>
              <div className={styles.row}>
                <div>
                  <div className={styles.rowLabel}>Retrieved sources per answer</div>
                  <div className={styles.rowHint}>How many passages are considered.</div>
                </div>
                <input className={styles.slider} type="range" min={2} max={8} defaultValue={4} />
              </div>
              <div className={styles.row}>
                <div>
                  <div className={styles.rowLabel}>Default market</div>
                  <div className={styles.rowHint}>Used when a question doesn't specify one.</div>
                </div>
                <select className={styles.select} defaultValue="auto">
                  <option value="auto">Auto-detect</option>
                  <option value="forex">Forex</option>
                  <option value="crypto">Crypto</option>
                  <option value="psx">PSX</option>
                  <option value="macro">Macro</option>
                </select>
              </div>
            </>
          )}

          {tab === 'Appearance' && (
            <>
              <h2 className={styles.panelTitle}>Appearance</h2>
              <div className={styles.row}>
                <div className={styles.rowLabel}>Theme</div>
                <div className={styles.themeToggle}>
                  <button
                    className={`${styles.themeOption} ${theme === 'light' ? styles.active : ''}`}
                    onClick={() => onThemeChange('light')}
                  >
                    Light
                  </button>
                  <button
                    className={`${styles.themeOption} ${theme === 'dark' ? styles.active : ''}`}
                    onClick={() => onThemeChange('dark')}
                  >
                    Dark
                  </button>
                </div>
              </div>
            </>
          )}

          {tab === 'Knowledge base' && (
            <>
              <h2 className={styles.panelTitle}>Knowledge base</h2>
              {kb === 'loading' && <p className={styles.rowHint}>Loading…</p>}
              {kb === 'error' && (
                <p className={styles.rowHint}>
                  Can't reach the API at {API_URL}. Start it with <code>rag serve</code> to see live
                  index stats here.
                </p>
              )}
              {typeof kb === 'object' && (
                <>
                  <div className={styles.docRow}>
                    <span className={styles.docName}>Documents indexed</span>
                    <span className={styles.docStatus}>{kb.documents}</span>
                  </div>
                  <div className={styles.docRow}>
                    <span className={styles.docName}>Chunks</span>
                    <span className={styles.docStatus}>{kb.chunks}</span>
                  </div>
                  <div className={styles.docRow}>
                    <span className={styles.docName}>Sources</span>
                    <span className={styles.docStatus}>{kb.sources}</span>
                  </div>
                  <div className={styles.docRow}>
                    <span className={styles.docName}>Newest document</span>
                    <span className={styles.docStatus}>
                      {kb.newestDocument ? kb.newestDocument.slice(0, 16).replace('T', ' ') : '—'}
                    </span>
                  </div>
                  {Object.entries(kb.markets).map(([market, count]) => (
                    <div key={market} className={styles.docRow}>
                      <span className={styles.docName} style={{ textTransform: 'capitalize' }}>
                        {market}
                      </span>
                      <span className={styles.docStatus}>{count} documents</span>
                    </div>
                  ))}
                </>
              )}
            </>
          )}

          {tab === 'Data & Privacy' && (
            <>
              <h2 className={styles.panelTitle}>Data &amp; Privacy</h2>
              <div className={styles.row}>
                <div>
                  <div className={styles.rowLabel}>Chat history</div>
                  <div className={styles.rowHint}>Stored locally on this device only.</div>
                </div>
                <button className={styles.dangerBtn}>Clear all chats</button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
