import { useState, useEffect } from 'react';
import api from '../utils/api';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const TIMES = ['7:00 AM', '8:00 AM', '9:00 AM', '10:00 AM', '12:00 PM', '2:00 PM', '5:00 PM', '7:00 PM'];

export default function SchedulePage({ posts }) {
  const [frequency, setFrequency] = useState(3);
  const [selectedDays, setSelectedDays] = useState(['Tue', 'Thu', 'Sat']);
  const [selectedTime, setSelectedTime] = useState('9:00 AM');
  const [autoPost, setAutoPost] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => { loadPrefs(); }, []);

  async function loadPrefs() {
    try {
      const prefs = await api.getPreferences();
      setFrequency(prefs.posting_frequency || 3);
      setSelectedDays(prefs.preferred_days || ['Tue', 'Thu', 'Sat']);
      setSelectedTime(prefs.preferred_time || '9:00 AM');
      setAutoPost(prefs.auto_post_enabled || false);
    } catch (e) {
      console.error('Failed to load preferences:', e);
    }
  }

  async function handleSave() {
    try {
      await api.updatePreferences({
        posting_frequency: frequency,
        preferred_days: selectedDays,
        preferred_time: selectedTime,
        auto_post_enabled: autoPost,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      console.error('Failed to save preferences:', e);
    }
  }

  function toggleDay(d) {
    setSelectedDays(prev =>
      prev.includes(d) ? prev.filter(x => x !== d) : [...prev, d]
    );
  }

  const scheduled = posts.filter(p => p.status === 'scheduled');

  return (
    <div style={styles.grid} className="animate-fade">
      {/* Left: Settings */}
      <div style={styles.column}>
        {/* Frequency */}
        <section style={styles.card}>
          <h3 style={styles.heading}>Posting frequency</h3>
          <div style={styles.freqRow}>
            <input
              type="range"
              min="1"
              max="5"
              value={frequency}
              onChange={e => setFrequency(+e.target.value)}
              style={styles.slider}
            />
            <span style={styles.freqValue}>{frequency}x/week</span>
          </div>
        </section>

        {/* Days */}
        <section style={styles.card}>
          <h3 style={styles.heading}>Preferred days</h3>
          <div style={styles.dayGrid}>
            {DAYS.map(d => (
              <button
                key={d}
                onClick={() => toggleDay(d)}
                style={{
                  ...styles.dayBtn,
                  ...(selectedDays.includes(d) ? styles.dayBtnActive : {}),
                }}
              >
                {d}
              </button>
            ))}
          </div>
        </section>

        {/* Time */}
        <section style={styles.card}>
          <h3 style={styles.heading}>Posting time</h3>
          <div style={styles.timeGrid}>
            {TIMES.map(t => (
              <button
                key={t}
                onClick={() => setSelectedTime(t)}
                style={{
                  ...styles.timeBtn,
                  ...(selectedTime === t ? styles.timeBtnActive : {}),
                }}
              >
                {t}
              </button>
            ))}
          </div>
          <div style={styles.aiTip}>
            <div style={styles.aiTipTitle}>AI recommendation</div>
            <div style={styles.aiTipText}>
              For India/IST audience, optimal posting: 8-9 AM and 5-7 PM on weekdays.
              The first 3-8 hours determine your reach.
            </div>
          </div>
        </section>

        {/* Autonomous mode */}
        <section style={styles.card}>
          <div style={styles.toggleRow}>
            <div>
              <div style={styles.toggleLabel}>Autonomous mode</div>
              <div style={styles.toggleDesc}>
                Auto-generate and publish without manual review
              </div>
            </div>
            <button
              onClick={() => setAutoPost(!autoPost)}
              style={styles.toggle(autoPost)}
              role="switch"
              aria-checked={autoPost}
            >
              <div style={styles.toggleThumb(autoPost)} />
            </button>
          </div>
          {autoPost && (
            <div style={styles.autoWarning}>
              Posts will be generated and published automatically on your schedule.
              Enable email notifications for review before posting.
            </div>
          )}
        </section>

        {/* Save */}
        <button onClick={handleSave} style={styles.saveBtn}>
          {saved ? '✓ Saved' : 'Save schedule settings'}
        </button>
      </div>

      {/* Right: Upcoming */}
      <div style={styles.column}>
        <section style={styles.card}>
          <h3 style={styles.heading}>Upcoming scheduled posts</h3>
          <div style={styles.scheduleList}>
            {scheduled.length === 0 ? (
              <div style={styles.empty}>
                No posts scheduled yet. Generate posts and schedule them from the Content tab.
              </div>
            ) : (
              scheduled.map(post => (
                <div key={post.id} style={styles.scheduleItem}>
                  <div style={styles.scheduleTitle}>{post.title}</div>
                  <div style={styles.scheduleDate}>
                    📅 {post.scheduled_date} at {post.scheduled_time}
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        <section style={styles.card}>
          <h3 style={styles.heading}>How autonomous mode works</h3>
          <div style={styles.stepList}>
            {[
              { n: '1', text: 'Scheduler triggers at your chosen day and time' },
              { n: '2', text: 'AI picks a trending topic in your active categories' },
              { n: '3', text: 'Researches the topic using web search' },
              { n: '4', text: 'Drafts a post matching your writing style' },
              { n: '5', text: 'Quality gate checks style match (revises if needed)' },
              { n: '6', text: 'Publishes to LinkedIn via API' },
            ].map(step => (
              <div key={step.n} style={styles.step}>
                <div style={styles.stepNum}>{step.n}</div>
                <div style={styles.stepText}>{step.text}</div>
              </div>
            ))}
          </div>
        </section>
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
    margin: '0 0 var(--space-4)',
  },
  freqRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-4)',
  },
  slider: {
    flex: 1,
    accentColor: 'var(--accent)',
  },
  freqValue: {
    fontSize: 'var(--text-xl)',
    fontWeight: 700,
    color: 'var(--accent-text)',
    minWidth: '80px',
    textAlign: 'right',
  },
  dayGrid: {
    display: 'flex',
    gap: 'var(--space-2)',
  },
  dayBtn: {
    width: '44px',
    height: '44px',
    borderRadius: 'var(--radius-md)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 'var(--text-xs)',
    fontWeight: 600,
    color: 'var(--text-tertiary)',
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    cursor: 'pointer',
    transition: 'all var(--duration) var(--ease)',
  },
  dayBtnActive: {
    background: 'var(--accent-muted)',
    borderColor: 'var(--border-active)',
    color: 'var(--accent-text)',
  },
  timeGrid: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 'var(--space-2)',
    marginBottom: 'var(--space-4)',
  },
  timeBtn: {
    padding: '6px 12px',
    borderRadius: 'var(--radius-full)',
    fontSize: 'var(--text-xs)',
    fontWeight: 500,
    color: 'var(--text-tertiary)',
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    cursor: 'pointer',
    transition: 'all var(--duration) var(--ease)',
  },
  timeBtnActive: {
    background: 'var(--success-muted)',
    borderColor: 'rgba(34,197,94,0.3)',
    color: 'var(--success)',
  },
  aiTip: {
    padding: 'var(--space-3) var(--space-4)',
    borderRadius: 'var(--radius-md)',
    background: 'var(--success-muted)',
    border: '1px solid rgba(34,197,94,0.15)',
  },
  aiTipTitle: {
    fontSize: 'var(--text-xs)',
    fontWeight: 600,
    color: 'var(--success)',
    marginBottom: 'var(--space-1)',
  },
  aiTipText: {
    fontSize: 'var(--text-sm)',
    color: 'var(--text-secondary)',
    lineHeight: 1.5,
  },
  toggleRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  toggleLabel: {
    fontSize: 'var(--text-md)',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  toggleDesc: {
    fontSize: 'var(--text-xs)',
    color: 'var(--text-tertiary)',
    marginTop: '2px',
  },
  toggle: (on) => ({
    width: '48px',
    height: '28px',
    borderRadius: '14px',
    background: on ? 'var(--accent)' : 'var(--bg-elevated)',
    border: `1px solid ${on ? 'var(--accent)' : 'var(--border)'}`,
    position: 'relative',
    cursor: 'pointer',
    transition: 'all var(--duration) var(--ease)',
    flexShrink: 0,
  }),
  toggleThumb: (on) => ({
    width: '22px',
    height: '22px',
    borderRadius: '11px',
    background: '#fff',
    position: 'absolute',
    top: '2px',
    left: on ? '23px' : '2px',
    transition: 'all var(--duration) var(--ease)',
  }),
  autoWarning: {
    marginTop: 'var(--space-3)',
    padding: 'var(--space-3) var(--space-4)',
    borderRadius: 'var(--radius-md)',
    background: 'var(--warning-muted)',
    border: '1px solid rgba(245,158,11,0.15)',
    fontSize: 'var(--text-sm)',
    color: 'var(--warning)',
    lineHeight: 1.5,
  },
  saveBtn: {
    width: '100%',
    padding: '12px',
    borderRadius: 'var(--radius-lg)',
    background: 'var(--accent)',
    color: '#fff',
    fontSize: 'var(--text-base)',
    fontWeight: 600,
    cursor: 'pointer',
    border: 'none',
    transition: 'all var(--duration) var(--ease)',
  },
  scheduleList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-3)',
  },
  scheduleItem: {
    padding: 'var(--space-3) var(--space-4)',
    borderRadius: 'var(--radius-md)',
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
  },
  scheduleTitle: {
    fontSize: 'var(--text-sm)',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  scheduleDate: {
    fontSize: 'var(--text-xs)',
    color: 'var(--text-tertiary)',
    marginTop: 'var(--space-1)',
  },
  empty: {
    textAlign: 'center',
    padding: 'var(--space-8)',
    color: 'var(--text-tertiary)',
    fontSize: 'var(--text-sm)',
  },
  stepList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-3)',
  },
  step: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 'var(--space-3)',
  },
  stepNum: {
    width: '24px',
    height: '24px',
    borderRadius: '50%',
    background: 'var(--accent-muted)',
    color: 'var(--accent-text)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 'var(--text-xs)',
    fontWeight: 700,
    flexShrink: 0,
  },
  stepText: {
    fontSize: 'var(--text-sm)',
    color: 'var(--text-secondary)',
    lineHeight: 1.5,
    paddingTop: '2px',
  },
};
