import { useState } from 'react';
import api from '../utils/api';

const STATUS_MAP = {
  draft: { label: 'Draft', color: 'var(--text-tertiary)', bg: 'var(--bg-elevated)' },
  scheduled: { label: 'Scheduled', color: 'var(--warning)', bg: 'var(--warning-muted)' },
  published: { label: 'Published', color: 'var(--success)', bg: 'var(--success-muted)' },
};

export default function ContentPage({ posts, config, onRefresh }) {
  const [filter, setFilter] = useState('all');
  const [editing, setEditing] = useState(null);
  const [editContent, setEditContent] = useState('');

  const categories = config?.categories || [];
  const filtered = filter === 'all' ? posts : posts.filter(p => p.status === filter);

  function getCategoryInfo(id) {
    return categories.find(c => c.id === id) || { icon: '📝', label: id };
  }

  async function handleSave() {
    if (!editing) return;
    try {
      await api.updatePost(editing.id, { content: editContent });
      setEditing(null);
      onRefresh?.();
    } catch (e) {
      console.error('Save failed:', e);
    }
  }

  async function handleDelete(id) {
    try {
      await api.deletePost(id);
      setEditing(null);
      onRefresh?.();
    } catch (e) {
      console.error('Delete failed:', e);
    }
  }

  async function handleSchedule(id) {
    try {
      await api.updatePost(id, {
        status: 'scheduled',
        scheduled_date: new Date(Date.now() + 86400000 * 2).toISOString().split('T')[0],
        scheduled_time: '09:00',
      });
      setEditing(null);
      onRefresh?.();
    } catch (e) {
      console.error('Schedule failed:', e);
    }
  }

  if (editing) {
    const cat = getCategoryInfo(editing.category);
    const status = STATUS_MAP[editing.status] || STATUS_MAP.draft;
    return (
      <div className="animate-fade">
        <button onClick={() => setEditing(null)} style={styles.backBtn}>
          ← Back to posts
        </button>
        <div style={styles.editorCard}>
          <div style={styles.editorHeader}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span>{cat.icon}</span>
              <span style={{ fontSize: 'var(--text-lg)', fontWeight: 700 }}>{editing.title}</span>
            </div>
            <span style={{ ...styles.badge, background: status.bg, color: status.color }}>
              {status.label}
            </span>
          </div>
          <textarea
            style={styles.editor}
            value={editContent}
            onChange={e => setEditContent(e.target.value)}
          />
          <div style={styles.editorActions}>
            <button onClick={handleSave} style={styles.saveBtn}>Save changes</button>
            {editing.status === 'draft' && (
              <button onClick={() => handleSchedule(editing.id)} style={styles.scheduleBtn}>
                Schedule
              </button>
            )}
            <button onClick={() => handleDelete(editing.id)} style={styles.deleteBtn}>
              Delete
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade">
      {/* Filters */}
      <div style={styles.filters}>
        {['all', 'draft', 'scheduled', 'published'].map(f => {
          const count = f === 'all' ? posts.length : posts.filter(p => p.status === f).length;
          return (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                ...styles.filterBtn,
                ...(filter === f ? styles.filterBtnActive : {}),
              }}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)} ({count})
            </button>
          );
        })}
      </div>

      {/* Post List */}
      <div style={styles.postList}>
        {filtered.length === 0 ? (
          <div style={styles.empty}>
            No {filter === 'all' ? '' : filter} posts yet. Generate your first post.
          </div>
        ) : (
          filtered.map(post => {
            const cat = getCategoryInfo(post.category);
            const status = STATUS_MAP[post.status] || STATUS_MAP.draft;
            return (
              <div
                key={post.id}
                style={styles.postCard}
                onClick={() => { setEditing(post); setEditContent(post.content); }}
                role="button"
                tabIndex={0}
              >
                <div style={styles.postHeader}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span>{cat.icon}</span>
                    <span style={styles.postTitle}>{post.title}</span>
                  </div>
                  <span style={{ ...styles.badge, background: status.bg, color: status.color }}>
                    {status.label}
                  </span>
                </div>
                <p style={styles.postExcerpt}>
                  {post.content?.substring(0, 160)}...
                </p>
                <div style={styles.postFooter}>
                  {post.scheduled_date && (
                    <span style={styles.footerItem}>
                      📅 {post.scheduled_date} {post.scheduled_time}
                    </span>
                  )}
                  {post.style_score > 0 && (
                    <span style={styles.footerItem}>
                      Style: {Math.round(post.style_score)}%
                    </span>
                  )}
                  <span style={styles.footerItem}>{cat.label}</span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

const styles = {
  filters: {
    display: 'flex',
    gap: 'var(--space-2)',
    marginBottom: 'var(--space-5)',
  },
  filterBtn: {
    padding: '6px 14px',
    borderRadius: 'var(--radius-full)',
    fontSize: 'var(--text-sm)',
    fontWeight: 500,
    color: 'var(--text-tertiary)',
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    cursor: 'pointer',
    transition: 'all var(--duration) var(--ease)',
  },
  filterBtnActive: {
    background: 'var(--accent-muted)',
    borderColor: 'var(--border-active)',
    color: 'var(--accent-text)',
  },
  postList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-3)',
  },
  postCard: {
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)',
    padding: 'var(--space-5)',
    cursor: 'pointer',
    transition: 'all var(--duration) var(--ease)',
  },
  postHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 'var(--space-3)',
  },
  postTitle: {
    fontSize: 'var(--text-md)',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  badge: {
    fontSize: 'var(--text-xs)',
    fontWeight: 600,
    padding: '3px 10px',
    borderRadius: 'var(--radius-sm)',
    flexShrink: 0,
  },
  postExcerpt: {
    fontSize: 'var(--text-sm)',
    color: 'var(--text-tertiary)',
    lineHeight: 1.5,
    margin: 0,
  },
  postFooter: {
    display: 'flex',
    gap: 'var(--space-4)',
    marginTop: 'var(--space-3)',
    paddingTop: 'var(--space-3)',
    borderTop: '1px solid var(--border)',
  },
  footerItem: {
    fontSize: 'var(--text-xs)',
    color: 'var(--text-tertiary)',
  },
  empty: {
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)',
    padding: 'var(--space-12)',
    textAlign: 'center',
    color: 'var(--text-tertiary)',
    fontSize: 'var(--text-sm)',
  },
  backBtn: {
    padding: '6px 14px',
    borderRadius: 'var(--radius-md)',
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    color: 'var(--text-secondary)',
    fontSize: 'var(--text-sm)',
    marginBottom: 'var(--space-4)',
    cursor: 'pointer',
  },
  editorCard: {
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-xl)',
    padding: 'var(--space-6)',
  },
  editorHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 'var(--space-4)',
  },
  editor: {
    minHeight: '350px',
    lineHeight: 1.7,
    fontSize: 'var(--text-base)',
    fontFamily: 'var(--font)',
  },
  editorActions: {
    display: 'flex',
    gap: 'var(--space-3)',
    marginTop: 'var(--space-4)',
  },
  saveBtn: {
    padding: '8px 20px',
    borderRadius: 'var(--radius-md)',
    background: 'var(--accent)',
    color: '#fff',
    fontSize: 'var(--text-sm)',
    fontWeight: 600,
    cursor: 'pointer',
    border: 'none',
  },
  scheduleBtn: {
    padding: '8px 20px',
    borderRadius: 'var(--radius-md)',
    background: 'var(--warning-muted)',
    border: '1px solid rgba(245,158,11,0.2)',
    color: 'var(--warning)',
    fontSize: 'var(--text-sm)',
    fontWeight: 600,
    cursor: 'pointer',
  },
  deleteBtn: {
    padding: '8px 20px',
    borderRadius: 'var(--radius-md)',
    background: 'var(--danger-muted)',
    border: '1px solid rgba(239,68,68,0.2)',
    color: 'var(--danger)',
    fontSize: 'var(--text-sm)',
    fontWeight: 500,
    cursor: 'pointer',
    marginLeft: 'auto',
  },
};
