import { useEffect, useRef, useState } from 'react';
import { ArrowUp, Paperclip, X } from 'lucide-react';
import type { UploadedFile } from '../../types';
import styles from './Composer.module.css';

interface ComposerProps {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function Composer({ onSend, disabled }: ComposerProps) {
  const [value, setValue] = useState('');
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);

  function handleSend() {
    if (!value.trim() || disabled) return;
    onSend(value.trim());
    setValue('');
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(e.target.files ?? []);
    const added: UploadedFile[] = picked.map((f) => ({
      id: `${f.name}-${Date.now()}`,
      name: f.name,
      status: 'processing',
    }));
    setFiles((prev) => [...prev, ...added]);
    // Mock indexing: flip to "Ready" after a short delay.
    added.forEach((file) => {
      setTimeout(() => {
        setFiles((prev) => prev.map((f) => (f.id === file.id ? { ...f, status: 'ready' } : f)));
      }, 1200);
    });
    e.target.value = '';
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.inner}>
        {files.length > 0 && (
          <div className={styles.chips}>
            {files.map((f) => (
              <span key={f.id} className={styles.chip}>
                {f.name}
                <span className={styles.chipStatus}>{f.status === 'ready' ? 'Ready' : 'Processing'}</span>
                <button
                  className={styles.chipRemove}
                  aria-label={`Remove ${f.name}`}
                  onClick={() => setFiles((prev) => prev.filter((x) => x.id !== f.id))}
                >
                  <X size={13} strokeWidth={1.5} />
                </button>
              </span>
            ))}
          </div>
        )}

        <div className={styles.composer}>
          <button
            className="icon-btn"
            aria-label="Attach file"
            onClick={() => fileInputRef.current?.click()}
          >
            <Paperclip size={17} strokeWidth={1.5} />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="visually-hidden"
            onChange={handleFileChange}
          />

          <textarea
            ref={textareaRef}
            className={styles.textarea}
            rows={1}
            placeholder="Message Market Intel"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            aria-label="Message"
          />

          <button
            className={styles.sendBtn}
            disabled={!value.trim() || disabled}
            onClick={handleSend}
            aria-label="Send message"
          >
            <ArrowUp size={16} strokeWidth={2} />
          </button>
        </div>
      </div>
    </div>
  );
}
