import { useState, useEffect } from 'react';
import api from '../utils/api';

export default function StylePage({ config }) {
  const [ownPost, setOwnPost] = useState('');
  const [inspPost, setInspPost] = useState('');
  const [ownCategory, setOwnCategory] = useState('');
  const [inspCategory, setInspCategory] = useState('');
  const [profile, setProfile] = useState(null);
  const [ownPosts, setOwnPosts] = useState([]);
  const [inspPosts, setInspPosts] = useState([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [message, setMessage] = useState('');

  const categories = config?.categories || [];

  useEffect(() => { loadData(); }, []);

  async function loadData() {
    try {
      const [profileData, ownData, inspData] = await Promise.all([
        api.getStyleProfile(),
        api.listStylePosts({ post_type: 'own' }),
        api.listStylePosts({ post_type: 'inspiration' }),
      ]);
      setProfile(profileData);
      setOwnPosts(ownData.posts || []);
      setInspPosts(inspData.posts || []);
    } catch (e) {
      console.error('Failed to load style data:', e);
    }
  }

  async function handleAddPost(type) {
    const content = type === 'own' ? ownPost : inspPost;
    const category = type === 'own' ? ownCategory : inspCategory;

    if (!content.trim()) return;

    try {
      const result = await api.addStylePost({
        content: content.trim(),
        post_type: type,
        category,
        user_id: 'default',
      });
      setMessage(result.message || 'Post added');
      if (type === 'own') setOwnPost('');
      else setInspPost('');
      loadData();
      setTimeout(() => setMessage(''), 3000);
    } catch (e) {
      setMessage('Failed to add post: ' + e.message);
    }
  }

  async function handleAnalyze() {
    setAnalyzing(true);
    try {
      const result = await api.analyzeStyle('default');
      setProfile(result);
      setMessage('Style profile updated');
      setTimeout(() => setMessage(''), 3000);
    } catch (e) {
      setMessage(e.message || 'Analysis failed');
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <div className="animate-fade">
      {message && (
        <div style={styles.toast}>{message}</div>
      )}

      <div style={styles.grid}>
        {/* Left column: Upload */}
        <div style={styles.column}>
          {/* Your posts */}
          <section style={styles.card}>
            <h3 style={styles.heading}>Your past posts</h3>
            <p style={styles.desc}>
              Paste your LinkedIn posts here. The AI learns your voice — sentence structure,
              formatting habits, emoji patterns, hook style.
            </p>

            <select
              style={styles.select}
              value={ownCategory}
              onChange={e => setOwnCategory(e.target.value)}
            >
              <option value="">Category (optional)</option>
              {categories.map(c => (
                <option key={c.id} value={c.id}>{c.icon} {c.label}</option>
              ))}
            </select>

            <textarea
              style={{ ...styles.textarea, marginTop: 'var(--space-3)' }}
              placeholder="Paste one of your LinkedIn posts here..."
              value={ownPost}
              onChange={e => setOwnPost(e.target.value)}
              rows={6}
            />

            <button onClick={() => handleAddPost('own')} style={styles.addBtn}>
              + Add to style profile
            </button>

            {ownPosts.length > 0 && (
              <div style={styles.postCount}>
                {ownPosts.length} post{ownPosts.length !== 1 ? 's' : ''} uploaded
              </div>
            )}
          </section>

          {/* Inspiration posts */}
          <section style={styles.card}>
            <h3 style={styles.heading}>Inspiration posts</h3>
            <p style={styles.desc}>
              Posts from others you admire. The AI captures their structure
              and approach — never copies their content.
            </p>

            <select
              style={styles.select}
              value={inspCategory}
              onChange={e => setInspCategory(e.target.value)}
            >
              <option value="">Category (optional)</option>
              {categories.map(c => (
                <option key={c.id} value={c.id}>{c.icon} {c.label}</option>
              ))}
            </select>

            <textarea
              style={{ ...styles.textarea, marginTop: 'var(--space-3)' }}
              placeholder="Paste a LinkedIn post you like..."
              value={inspPost}
              onChange={e => setInspPost(e.target.value)}
              rows={5}
            />

            <button onClick={() => handleAddPost('inspiration')} style={styles.addBtn}>
              + Add inspiration ({inspPosts.length} saved)
            </button>
          </section>
        </div>

        {/* Right column: Profile */}
        <div style={styles.column}>
          <section style={styles.card}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
              <h3 style={styles.heading}>Detected style profile</h3>
              <button
                onClick={handleAnalyze}
                style={styles.analyzeBtn}
              >
                {analyzing ? 'Analyzing...' : 'Re-analyze'}
              </button>
            </div>

            {profile && profile.post_count > 0 ? (
              <div style={styles.profileGrid}>
                {[
                  { label: 'Voice', value: profile.voice_description || 'Upload posts to detect' },
                  { label: 'Hook style', value: profile.hook_style || '—' },
                  { label: 'CTA style', value: profile.cta_style || '—' },
                  { label: 'Formatting', value: profile.formatting_style || '—' },
                  { label: 'Emoji usage', value: profile.emoji_style || '—' },
                  { label: 'Avg. length', value: profile.avg_word_count ? `${profile.avg_word_count} words` : '—' },
                  { label: 'Code blocks', value: profile.uses_code_blocks ? 'Yes' : 'No' },
                  { label: 'Arrow bullets', value: profile.uses_arrow_bullets ? 'Yes (→)' : 'No' },
                ].map((item, i) => (
                  <div key={i} style={styles.profileItem}>
                    <div style={styles.profileLabel}>{item.label}</div>
                    <div style={styles.profileValue}>{item.value}</div>
                  </div>
                ))}

                {profile.tone_keywords?.length > 0 && (
                  <div style={{ ...styles.profileItem, gridColumn: '1 / -1' }}>
                    <div style={styles.profileLabel}>Tone keywords</div>
                    <div style={styles.tagRow}>
                      {profile.tone_keywords.map((kw, i) => (
                        <span key={i} style={styles.toneChip}>{kw}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div style={styles.emptyProfile}>
                <div style={{ fontSize: '28px', opacity: 0.3, marginBottom: 'var(--space-3)' }}>◎</div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-tertiary)' }}>
                  Upload at least 2-3 of your past posts, then click "Re-analyze" to generate your style profile.
                </div>
              </div>
            )}
          </section>

          {/* Tone overrides per category */}
          <section style={styles.card}>
            <h3 style={styles.heading}>Tone per category</h3>
            <p style={styles.desc}>
              Set different tones for different categories. If not set, the global default is used.
            </p>
            <div style={styles.toneGrid}>
              {categories.map(cat => (
                <div key={cat.id} style={styles.toneRow}>
                  <span style={styles.toneLabel}>{cat.icon} {cat.label}</span>
                  <select style={styles.toneSelect}>
                    <option value="">Use default</option>
                    {(config?.tones || []).map(t => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </section>
        </div>
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
  column: {
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
  heading: {
    fontSize: 'var(--text-base)',
    fontWeight: 600,
    color: 'var(--text-primary)',
    margin: 0,
  },
  desc: {
    fontSize: 'var(--text-sm)',
    color: 'var(--text-tertiary)',
    marginTop: 'var(--space-2)',
    marginBottom: 'var(--space-4)',
    lineHeight: 1.5,
  },
  select: {
    width: '100%',
    padding: 'var(--space-3) var(--space-4)',
    borderRadius: 'var(--radius-md)',
    background: 'var(--bg-input)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontSize: 'var(--text-sm)',
    fontFamily: 'var(--font)',
  },
  textarea: { minHeight: '120px' },
  addBtn: {
    width: '100%',
    marginTop: 'var(--space-3)',
    padding: '10px',
    borderRadius: 'var(--radius-md)',
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    color: 'var(--text-secondary)',
    fontSize: 'var(--text-sm)',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all var(--duration) var(--ease)',
  },
  postCount: {
    marginTop: 'var(--space-3)',
    fontSize: 'var(--text-xs)',
    color: 'var(--success)',
    fontWeight: 600,
  },
  analyzeBtn: {
    padding: '6px 14px',
    borderRadius: 'var(--radius-md)',
    background: 'var(--accent-muted)',
    border: '1px solid var(--border-active)',
    color: 'var(--accent-text)',
    fontSize: 'var(--text-xs)',
    fontWeight: 600,
    cursor: 'pointer',
  },
  profileGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 'var(--space-3)',
  },
  profileItem: {
    padding: 'var(--space-3)',
    borderRadius: 'var(--radius-md)',
    background: 'var(--bg-elevated)',
  },
  profileLabel: {
    fontSize: 'var(--text-xs)',
    color: 'var(--text-tertiary)',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    marginBottom: 'var(--space-1)',
  },
  profileValue: {
    fontSize: 'var(--text-sm)',
    color: 'var(--text-primary)',
    fontWeight: 500,
    lineHeight: 1.4,
  },
  tagRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 'var(--space-2)',
    marginTop: 'var(--space-2)',
  },
  toneChip: {
    padding: '3px 10px',
    borderRadius: 'var(--radius-full)',
    background: 'var(--accent-muted)',
    color: 'var(--accent-text)',
    fontSize: 'var(--text-xs)',
    fontWeight: 500,
  },
  emptyProfile: {
    textAlign: 'center',
    padding: 'var(--space-8)',
  },
  toneGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-2)',
    marginTop: 'var(--space-3)',
  },
  toneRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 'var(--space-3)',
    padding: 'var(--space-2) 0',
  },
  toneLabel: {
    fontSize: 'var(--text-sm)',
    color: 'var(--text-secondary)',
    whiteSpace: 'nowrap',
  },
  toneSelect: {
    width: '160px',
    padding: '6px 10px',
    borderRadius: 'var(--radius-sm)',
    background: 'var(--bg-input)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontSize: 'var(--text-xs)',
    fontFamily: 'var(--font)',
  },
  toast: {
    marginBottom: 'var(--space-4)',
    padding: 'var(--space-3) var(--space-4)',
    borderRadius: 'var(--radius-md)',
    background: 'var(--success-muted)',
    color: 'var(--success)',
    fontSize: 'var(--text-sm)',
    border: '1px solid rgba(34,197,94,0.2)',
  },
};
