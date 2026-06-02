const BASE = '/api';

async function request(path, opts = {}) {
  const headers = { ...opts.headers };
  // Don't set Content-Type for FormData (browser sets boundary automatically)
  if (!(opts.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers,
    body: opts.body instanceof FormData
      ? opts.body
      : opts.body
        ? (typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body))
        : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

const api = {
  health: () => request('/health'),
  getConfig: () => request('/config'),

  // Generation
  generatePost: (data) => request('/generate', { method: 'POST', body: data }),

  // Posts CRUD
  listPosts: (p = {}) => { const q = new URLSearchParams(p).toString(); return request(`/posts${q ? '?' + q : ''}`); },
  getPost: (id) => request(`/posts/${id}`),
  updatePost: (id, d) => request(`/posts/${id}`, { method: 'PUT', body: d }),
  deletePost: (id) => request(`/posts/${id}`, { method: 'DELETE' }),

  // Style
  addStylePost: (d) => request('/style/posts', { method: 'POST', body: d }),
  listStylePosts: (p = {}) => { const q = new URLSearchParams(p).toString(); return request(`/style/posts${q ? '?' + q : ''}`); },
  getStyleCounts: (uid = 'default') => request(`/style/counts?user_id=${uid}`),
  deleteStylePost: (id) => request(`/style/posts/${id}`, { method: 'DELETE' }),
  deleteStylePostsBulk: (p = {}) => {
    const q = new URLSearchParams(p).toString();
    return request(`/style/posts${q ? '?' + q : ''}`, { method: 'DELETE' });
  },
  uploadStyleFile: (file, postType = 'own', category = '', userId = 'default') => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('post_type', postType);
    fd.append('category', category);
    fd.append('user_id', userId);
    return request('/style/upload', { method: 'POST', body: fd });
  },
  analyzeStyle: (uid = 'default') => request('/style/analyze', { method: 'POST', body: { user_id: uid } }),
  getStyleProfile: (uid = 'default') => request(`/style/profile?user_id=${uid}`),

  // Preferences
  getPreferences: (uid = 'default') => request(`/preferences?user_id=${uid}`),
  updatePreferences: (d, uid = 'default') => request(`/preferences?user_id=${uid}`, { method: 'PUT', body: d }),

  // Models
  listModels: () => request('/models'),
  selectModel: (modelId, uid = 'default') => request(`/models/select?model_id=${encodeURIComponent(modelId)}&user_id=${uid}`, { method: 'PUT' }),

  // Custom Rules
  getRules: (uid = 'default') => request(`/rules?user_id=${uid}`),
  updateRules: (rules, uid = 'default') => request(`/rules?rules=${encodeURIComponent(rules)}&user_id=${uid}`, { method: 'PUT' }),

  // Carousel
  generateCarousel: (d) => request('/carousel', { method: 'POST', body: d }),

  // Hooks
  generateHooks: (d) => request('/hooks', { method: 'POST', body: d }),
  applyHook: (d) => request('/hooks/apply', { method: 'POST', body: d }),

  // Comments
  draftReply: (d) => request('/comments/reply', { method: 'POST', body: d }),
  draftProactive: (d) => request('/comments/proactive', { method: 'POST', body: d }),
  batchReplies: (d) => request('/comments/batch', { method: 'POST', body: d }),

  // Repurpose
  repurpose: (d) => request('/repurpose', { method: 'POST', body: d }),

  // Hashtags
  optimizeHashtags: (content, cat = '', count = 4) =>
    request(`/hashtags?content=${encodeURIComponent(content)}&category=${cat}&count=${count}`, { method: 'POST' }),

  // Engagement
  predictEngagement: (content, cat = '', fmt = '') =>
    request(`/predict?content=${encodeURIComponent(content)}&category=${cat}&format=${fmt}`, { method: 'POST' }),
  getAnalytics: (uid = 'default') => request(`/analytics?user_id=${uid}`),

  // LinkedIn
  linkedinStatus: () => request('/linkedin/status'),
  publishToLinkedIn: (d) => request('/linkedin/post', { method: 'POST', body: d }),
};

export default api;
