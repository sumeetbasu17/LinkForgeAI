import { useState } from 'react';
import api from '../utils/api';

export default function GeneratePage({ config, onPostCreated }) {
  const [category, setCategory] = useState('');
  const [topic, setTopic] = useState('');
  const [format, setFormat] = useState('story');
  const [tone, setTone] = useState('Conversational');
  const [context, setContext] = useState('');
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const categories = config?.categories || [];
  const formats = config?.formats || [];
  const tones = config?.tones || [];

  async function handleGenerate() {
    if (!category) {
      setError('Pick a category first');
      return;
    }
    setError('');
    setGenerating(true);
    setResult(null);

    try {
      const data = await api.generatePost({
        category,
        topic: topic || '',
        format,
        tone,
        user_id: 'default',
      });
      setResult(data);
      onPostCreated?.();
    } catch (e) {
      setError(e.message || 'Generation failed. Is the backend running?');
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div style={styles.grid}>
      {/* Left: Controls */}
      <div style={styles.controls}>
        {/* Category */}
        <section style={styles.card}>
          <h3 style={styles.label}>Category</h3>
          <div style={styles.tagGrid}>
            {categories.map(cat => (
              <button
                key={cat.id}
                onClick={() => setCategory(cat.id)}
                style={{
                  ...styles.tag,
                  ...(category === cat.id ? styles.tagActive : {}),
                }}
              >
                <span>{cat.icon}</span>
                <span>{cat.label}</span>
              </button>
            ))}
          </div>
        </section>

        {/* Topic */}
        <section style={styles.card}>
          <h3 style={styles.label}>Topic</h3>
          <input
            style={styles.input}
            placeholder="Leave empty for AI to pick a trending topic..."
            value={topic}
            onChange={e => setTopic(e.target.value)}
          />
          <textarea
            style={{ ...styles.textarea, marginTop: 'var(--space-3)' }}
            placeholder="Add context, personal story, or key points to include..."
            value={context}
            onChange={e => setContext(e.target.value)}
            rows={3}
          />
        </section>

        {/* Format */}
        <section style={styles.card}>
          <h3 style={styles.label}>Format</h3>
          <div style={styles.formatGrid}>
            {formats.map(f => (
              <button
                key={f.id}
                onClick={() => setFormat(f.id)}
                style={{
                  ...styles.formatBtn,
                  ...(format === f.id ? styles.formatBtnActive : {}),
                }}
              >
                <div style={styles.formatLabel}>{f.label}</div>
                <div style={styles.formatDesc}>{f.description}</div>
              </button>
            ))}
          </div>
        </section>

        {/* Tone */}
        <section style={styles.card}>
          <h3 style={styles.label}>Tone</h3>
          <div style={styles.tagGrid}>
            {tones.map(t => (
              <button
                key={t}
                onClick={() => setTone(t)}
                style={{
                  ...styles.toneTag,
                  ...(tone === t ? styles.toneTagActive : {}),
                }}
              >
                {t}
              </button>
            ))}
          </div>
        </section>

        {/* Generate Button — never disabled, shows state */}
        <button
          onClick={handleGenerate}
          style={{
            ...styles.generateBtn,
            ...(generating ? styles.generateBtnLoading : {}),
          }}
        >
          {generating ? (
            <>
              <span className="animate-spin" style={{ display: 'inline-block' }}>⚙</span>
              Generating with AI...
            </>
          ) : (
            <>✦ Generate post</>
          )}
        </button>

        {error && (
          <div style={styles.error}>{error}</div>
        )}
      </div>

      {/* Right: Result */}
      <div style={styles.resultArea}>
        {result ? (
          <div style={styles.resultCard} className="animate-slide">
            <div style={styles.resultHeader}>
              <div>
                <div style={styles.resultTitle}>{result.title}</div>
                <div style={styles.resultMeta}>
                  {result.selected_topic && (
                    <span style={styles.metaItem}>Topic: {result.selected_topic}</span>
                  )}
                  <span style={styles.scoreChip(result.style_score)}>
                    Style match: {Math.round(result.style_score)}%
                  </span>
                  {result.revision_count > 0 && (
                    <span style={styles.metaItem}>Revised {result.revision_count}x</span>
                  )}
                </div>
              </div>
              <span style={styles.statusBadge}>Draft</span>
            </div>

            <div style={styles.postPreview}>
              {result.content}
            </div>

            <div style={styles.resultActions}>
              <button style={styles.actionBtn} onClick={() => {
                navigator.clipboard.writeText(result.content);
              }}>
                Copy
              </button>
              <button style={styles.actionBtnPrimary} onClick={handleGenerate}>
                Regenerate
              </button>
            </div>
          </div>
        ) : (
          <div style={styles.emptyState}>
            <div style={styles.emptyIcon}>✦</div>
            <div style={styles.emptyTitle}>Configure and generate</div>
            <div style={styles.emptyDesc}>
              Pick a category, optionally set a topic, choose format and tone, then generate.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const styles = {
  grid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 'var(--space-6)',
    alignItems: 'start',
  },
  controls: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-5)',
  },
  card: {
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)',
    padding: 'var(--space-5)',
  },
  label: {
    fontSize: 'var(--text-xs)',
    fontWeight: 600,
    color: 'var(--text-tertiary)',
    textTransform: 'uppercase',
    letterSpacing: '1px',
    marginBottom: 'var(--space-3)',
  },
  tagGrid: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 'var(--space-2)',
  },
  tag: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 'var(--space-2)',
    padding: '6px 14px',
    borderRadius: 'var(--radius-full)',
    fontSize: 'var(--text-sm)',
    fontWeight: 500,
    color: 'var(--text-tertiary)',
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    transition: 'all var(--duration) var(--ease)',
    cursor: 'pointer',
  },
  tagActive: {
    background: 'var(--accent-muted)',
    borderColor: 'var(--border-active)',
    color: 'var(--accent-text)',
  },
  formatGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 'var(--space-2)',
  },
  formatBtn: {
    padding: '10px 14px',
    borderRadius: 'var(--radius-md)',
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    textAlign: 'left',
    transition: 'all var(--duration) var(--ease)',
    cursor: 'pointer',
  },
  formatBtnActive: {
    background: 'var(--accent-muted)',
    borderColor: 'var(--border-active)',
  },
  formatLabel: {
    fontSize: 'var(--text-sm)',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  formatDesc: {
    fontSize: 'var(--text-xs)',
    color: 'var(--text-tertiary)',
    marginTop: '2px',
  },
  toneTag: {
    padding: '6px 14px',
    borderRadius: 'var(--radius-full)',
    fontSize: 'var(--text-sm)',
    fontWeight: 500,
    color: 'var(--text-tertiary)',
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    transition: 'all var(--duration) var(--ease)',
    cursor: 'pointer',
  },
  toneTagActive: {
    background: 'var(--accent-muted)',
    borderColor: 'var(--border-active)',
    color: 'var(--accent-text)',
  },
  input: {},
  textarea: { minHeight: '70px' },
  generateBtn: {
    width: '100%',
    padding: '14px',
    borderRadius: 'var(--radius-lg)',
    background: 'linear-gradient(135deg, var(--accent), #8B5CF6)',
    color: '#fff',
    fontSize: 'var(--text-md)',
    fontWeight: 600,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 'var(--space-2)',
    transition: 'all var(--duration) var(--ease)',
    boxShadow: '0 4px 20px rgba(99,102,241,0.25)',
    cursor: 'pointer',
    border: 'none',
  },
  generateBtnLoading: {
    opacity: 0.85,
  },
  error: {
    padding: 'var(--space-3) var(--space-4)',
    borderRadius: 'var(--radius-md)',
    background: 'var(--danger-muted)',
    color: 'var(--danger)',
    fontSize: 'var(--text-sm)',
    border: '1px solid rgba(239,68,68,0.2)',
  },
  resultArea: {
    position: 'sticky',
    top: 'var(--space-8)',
  },
  resultCard: {
    background: 'var(--bg-surface)',
    border: '1px solid var(--border-active)',
    borderRadius: 'var(--radius-xl)',
    padding: 'var(--space-6)',
  },
  resultHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 'var(--space-4)',
  },
  resultTitle: {
    fontSize: 'var(--text-lg)',
    fontWeight: 700,
    color: 'var(--text-primary)',
    marginBottom: 'var(--space-2)',
  },
  resultMeta: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 'var(--space-2)',
    alignItems: 'center',
  },
  metaItem: {
    fontSize: 'var(--text-xs)',
    color: 'var(--text-tertiary)',
  },
  scoreChip: (score) => ({
    fontSize: 'var(--text-xs)',
    fontWeight: 600,
    padding: '2px 8px',
    borderRadius: 'var(--radius-sm)',
    background: score >= 70 ? 'var(--success-muted)' : 'var(--warning-muted)',
    color: score >= 70 ? 'var(--success)' : 'var(--warning)',
  }),
  statusBadge: {
    fontSize: 'var(--text-xs)',
    fontWeight: 600,
    padding: '3px 10px',
    borderRadius: 'var(--radius-sm)',
    background: 'var(--info-muted)',
    color: 'var(--info)',
    flexShrink: 0,
  },
  postPreview: {
    background: 'var(--bg-primary)',
    borderRadius: 'var(--radius-lg)',
    padding: 'var(--space-5)',
    fontSize: 'var(--text-base)',
    color: 'var(--text-secondary)',
    lineHeight: 1.7,
    whiteSpace: 'pre-wrap',
    maxHeight: '450px',
    overflowY: 'auto',
    border: '1px solid var(--border)',
  },
  resultActions: {
    display: 'flex',
    gap: 'var(--space-3)',
    marginTop: 'var(--space-4)',
  },
  actionBtn: {
    padding: '8px 18px',
    borderRadius: 'var(--radius-md)',
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    color: 'var(--text-secondary)',
    fontSize: 'var(--text-sm)',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all var(--duration) var(--ease)',
  },
  actionBtnPrimary: {
    padding: '8px 18px',
    borderRadius: 'var(--radius-md)',
    background: 'var(--accent-muted)',
    border: '1px solid var(--border-active)',
    color: 'var(--accent-text)',
    fontSize: 'var(--text-sm)',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all var(--duration) var(--ease)',
  },
  emptyState: {
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-xl)',
    padding: 'var(--space-12) var(--space-8)',
    textAlign: 'center',
  },
  emptyIcon: {
    fontSize: '40px',
    color: 'var(--text-tertiary)',
    opacity: 0.4,
    marginBottom: 'var(--space-4)',
  },
  emptyTitle: {
    fontSize: 'var(--text-md)',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    marginBottom: 'var(--space-2)',
  },
  emptyDesc: {
    fontSize: 'var(--text-sm)',
    color: 'var(--text-tertiary)',
  },
};
