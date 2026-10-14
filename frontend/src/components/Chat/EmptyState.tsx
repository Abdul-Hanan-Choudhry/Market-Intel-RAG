import { exampleQuestions } from '../../data/mockData';
import styles from './EmptyState.module.css';

interface EmptyStateProps {
  onPick: (question: string) => void;
}

export function EmptyState({ onPick }: EmptyStateProps) {
  return (
    <div className={styles.wrap}>
      <p className={styles.greeting}>What are you tracking today?</p>
      <div className={styles.examples}>
        {exampleQuestions.map((q) => (
          <button key={q} className={styles.example} onClick={() => onPick(q)}>
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
