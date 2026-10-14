import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import type { ThemeMode } from '../../types';
import styles from './SettingsModal.module.css';

type Tab = 'General' | 'Appearance' | 'Knowledge base' | 'Data & Privacy' | 'Account';
const TABS: Tab[] = ['General', 'Appearance', 'Knowledge base', 'Data & Privacy', 'Account'];

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
  theme: ThemeMode;
  onThemeChange: (theme: ThemeMode) => void;
}

const MOCK_DOCS = [
  { name: 'fxstreet_feed.jsonl', status: 'Ready' },
  { name: 'sbp_monetary_policy_q3.pdf', status: 'Ready' },
  { name: 'psx_daily_bulletin_oct.pdf', status: 'Processing' },
];

export function SettingsModal({ open, onClose, theme, onThemeChange }: SettingsModalProps) {
  const [tab, setTab] = useState<Tab>('General');

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

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
              {MOCK_DOCS.map((d) => (
                <div key={d.name} className={styles.docRow}>
                  <span className={styles.docName}>{d.name}</span>
                  <span className={styles.docStatus}>{d.status}</span>
                </div>
              ))}
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

          {tab === 'Account' && (
            <>
              <h2 className={styles.panelTitle}>Account</h2>
              <div className={styles.row}>
                <div className={styles.rowLabel}>Name</div>
                <span className={styles.docStatus}>Abdul Hanan</span>
              </div>
              <div className={styles.row}>
                <div className={styles.rowLabel}>Email</div>
                <span className={styles.docStatus}>abdulhananch404@gmail.com</span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
