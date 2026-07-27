import { useState, useEffect, useCallback, useRef } from 'react';
import api from './utils/api.js';

const font = `'Instrument Sans', 'DM Sans', system-ui, sans-serif`;
const S = {
  card: { background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '14px', padding: '20px' },
  input: { width: '100%', padding: '10px 14px', borderRadius: '10px', boxSizing: 'border-box', border: '1px solid var(--border)', background: 'var(--bg-input)', color: 'var(--text)', fontSize: '14px', fontFamily: font, outline: 'none' },
  textarea: { width: '100%', padding: '12px 14px', borderRadius: '10px', boxSizing: 'border-box', border: '1px solid var(--border)', background: 'var(--bg-input)', color: 'var(--text)', fontSize: '14px', fontFamily: font, outline: 'none', resize: 'vertical', minHeight: '100px', lineHeight: 1.6 },
  btn: (v='primary') => ({ padding:'10px 20px', borderRadius:'10px', border:'none', cursor:'pointer', fontSize:'14px', fontWeight:600, fontFamily:font, display:'inline-flex', alignItems:'center', gap:'8px', transition:'all 0.15s',
    ...(v==='primary'?{background:'var(--accent)',color:'#fff'}:v==='danger'?{background:'var(--danger-bg)',color:'var(--danger)'}:v==='success'?{background:'var(--success)',color:'#fff'}:{background:'var(--bg-input)',color:'var(--text-muted)',border:'1px solid var(--border)'}),
  }),
  label: { fontSize:'12px', fontWeight:600, color:'var(--text-muted)', textTransform:'uppercase', letterSpacing:'0.7px', marginBottom:'8px', display:'block' },
  tag: (a,c) => ({ display:'inline-flex', alignItems:'center', gap:'6px', padding:'6px 14px', borderRadius:'20px', cursor:'pointer', fontSize:'13px', fontWeight:500, transition:'all 0.15s', userSelect:'none', background:a?(c?c+'20':'var(--accent-bg)'):'var(--bg-input)', border:`1px solid ${a?(c?c+'50':'var(--accent)'):'var(--border)'}`, color:a?(c||'var(--accent)'):'var(--text-muted)' }),
  badge: c => ({ display:'inline-flex', padding:'3px 10px', borderRadius:'6px', fontSize:'11px', fontWeight:600, background:c+'18', color:c }),
  grid2: { display:'grid', gridTemplateColumns:'1fr 1fr', gap:'20px' },
  col: { display:'flex', flexDirection:'column', gap:'16px' },
  preview: { background:'var(--bg-input)', borderRadius:'10px', padding:'18px', fontSize:'14px', lineHeight:1.7, whiteSpace:'pre-wrap', maxHeight:'500px', overflowY:'auto', border:'1px solid var(--border)' },
};
function Toast({msg,type,onClose}){useEffect(()=>{const t=setTimeout(onClose,4000);return()=>clearTimeout(t)},[onClose]);if(!msg)return null;return<div style={{position:'fixed',bottom:'24px',right:'24px',zIndex:100,padding:'12px 20px',borderRadius:'10px',background:type==='error'?'var(--danger)':'var(--success)',color:'#fff',fontSize:'14px',fontWeight:500,fontFamily:font,boxShadow:'0 8px 32px rgba(0,0,0,0.3)',animation:'slideIn 0.3s ease'}}>{msg}</div>}
function Empty({icon,text,sub}){return<div style={{...S.card,display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',minHeight:'300px',textAlign:'center'}}><div style={{fontSize:'48px',marginBottom:'14px',opacity:0.4}}>{icon}</div><div style={{fontSize:'15px',color:'var(--text-muted)'}}>{text}</div>{sub&&<div style={{fontSize:'13px',color:'var(--text-dim)',marginTop:'4px'}}>{sub}</div>}</div>}
function Loader({text}){return<div style={{...S.card,textAlign:'center',padding:'48px',color:'var(--text-dim)'}}>{text||'Loading...'}</div>}

// ─── 1. Generate (receives state from parent) ────────────────────
function GenerateTab({config,toast,genState,setGenState}){
  const [gen,setGen]=useState(false);const [engagement,setEngagement]=useState(null);const [liStatus,setLiStatus]=useState(null);const [publishing,setPublishing]=useState(false);
  const [prefs,setPrefs]=useState(null);const [fromSettings,setFromSettings]=useState('');
  const [postImg,setPostImg]=useState(null);const [imgBusy,setImgBusy]=useState(false);
  useEffect(()=>{api.linkedinStatus().then(setLiStatus).catch(()=>{})},[]);
  const {cat,topic,fmt,tone,result}=genState;
  const set=(k,v)=>setGenState(p=>({...p,[k]:v}));

  // Settings supply the starting point; anything picked here wins over them.
  useEffect(()=>{(async()=>{try{
    const p=await api.getPreferences();setPrefs(p);
    setGenState(prev=>({...prev,
      fmt:prev.fmt||p.default_format||'story',
      tone:prev.tone||p.default_tone||'Conversational'}));
  }catch{}})()},[setGenState]);

  const pickCategory=id=>{
    set('cat',id);
    const t=prefs?.tone_overrides?.[id];
    if(t&&t!==tone){set('tone',t);setFromSettings(t)}
    else if(!t)setFromSettings('');
  };
  const pickTone=t=>{set('tone',t);setFromSettings('')};

  const generate=async()=>{if(!cat){toast('Select a category','error');return}setGen(true);set('result',null);setEngagement(null);setPostImg(null);try{const r=await api.generatePost({category:cat,topic,format:fmt,tone});set('result',r);toast('Post generated!');try{const e=await api.predictEngagement(r.content,cat,fmt);setEngagement(e)}catch{}}catch(e){toast(e.message,'error')}finally{setGen(false)}};
  const publish=async()=>{if(!result)return;setPublishing(true);try{await api.publishToLinkedIn({post_id:result.post_id});toast('Published!')}catch(e){toast(e.message,'error')}finally{setPublishing(false)}};
  const makeImage=async(arch='')=>{if(!result)return;setImgBusy(true);
    try{const r=await api.generatePostImage({post_id:result.post_id,content:result.content,archetype:arch,
      ...(arch||!result.image_payload||!Object.keys(result.image_payload).length?{}:{payload:result.image_payload})});
      if(!r.generated){setPostImg(null);toast(r.message)}else{setPostImg(r);toast(`${r.archetype} rendered`)}}
    catch(e){toast(e.message,'error')}finally{setImgBusy(false)}};
  const dropImage=async()=>{if(!postImg)return;try{await api.deletePostImage(postImg.id);setPostImg(null);toast('Image removed')}catch(e){toast(e.message,'error')}};

  return(<div style={S.grid2}>
    <div style={S.col}>
      <div style={S.card}><label style={S.label}>Topic (optional)</label><input style={S.input} placeholder="Leave blank for AI to pick trending..." value={topic} onChange={e=>set('topic',e.target.value)}/></div>
      <div style={S.card}><label style={S.label}>Category</label><div style={{display:'flex',flexWrap:'wrap',gap:'8px'}}>{(config?.categories||[]).map(c=><span key={c.id} style={S.tag(cat===c.id)} onClick={()=>pickCategory(c.id)}>{c.icon} {c.label}</span>)}</div></div>
      <div style={S.card}><label style={S.label}>Format</label><div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'8px'}}>{(config?.formats||[]).map(f=><div key={f.id} onClick={()=>set('fmt',f.id)} style={{padding:'10px 14px',borderRadius:'10px',cursor:'pointer',background:fmt===f.id?'var(--accent-bg)':'var(--bg-input)',border:`1px solid ${fmt===f.id?'var(--accent)':'var(--border)'}`}}><div style={{fontSize:'13px',fontWeight:600,color:fmt===f.id?'var(--accent)':'var(--text-muted)'}}>{f.label}</div><div style={{fontSize:'11px',color:'var(--text-dim)',marginTop:'2px'}}>{f.description}</div></div>)}</div></div>
      <div style={S.card}><label style={S.label}>Tone</label><div style={{display:'flex',flexWrap:'wrap',gap:'8px'}}>{(config?.tones||[]).map(t=><span key={t} style={S.tag(tone===t)} onClick={()=>pickTone(t)}>{t}</span>)}</div>
        <div style={{fontSize:'11px',color:'var(--text-dim)',marginTop:'8px'}}>{fromSettings?`Set to ${fromSettings} by this category's tone in Settings — pick another to override it.`:'This is the tone the post is written in. It overrides Settings.'}</div>
      </div>
      <button style={{...S.btn(),justifyContent:'center',padding:'14px',opacity:gen?0.7:1}} onClick={generate} disabled={gen}>{gen?'⏳ Generating...':'✨ Generate post'}</button>
    </div>
    <div style={S.col}>
      {result?(<div style={{...S.card,borderColor:'var(--accent)'}}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'6px'}}><span style={{fontSize:'16px',fontWeight:700}}>{result.title}</span><span style={S.badge('#10B981')}>Style: {Math.round(result.style_score)}</span></div>
        {result.selected_topic&&<div style={{fontSize:'12px',color:'var(--text-dim)',marginBottom:'10px'}}>Topic: {result.selected_topic}</div>}
        <div style={S.preview}>{result.content}</div>
        {engagement&&<div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:'8px',marginTop:'14px'}}>{[{l:'Overall',v:engagement.overall_score,c:'#6366F1'},{l:'Dwell',v:engagement.dwell_time_score,c:'#3B82F6'},{l:'Save',v:engagement.save_potential,c:'#10B981'},{l:'Comment',v:engagement.comment_potential,c:'#F59E0B'}].map((s,i)=><div key={i} style={{textAlign:'center',padding:'10px',borderRadius:'10px',background:'var(--bg-input)'}}><div style={{fontSize:'20px',fontWeight:700,color:s.c}}>{s.v}</div><div style={{fontSize:'10px',color:'var(--text-dim)',textTransform:'uppercase',marginTop:'2px'}}>{s.l}</div></div>)}</div>}
        <div style={{marginTop:'14px',padding:'12px',borderRadius:'10px',background:'var(--bg-input)',border:'1px solid var(--border)'}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:'10px',flexWrap:'wrap'}}>
            <div style={{fontSize:'12px',color:'var(--text-dim)'}}>
              {result.wants_image
                ?<>Suggested image: <b style={{color:'var(--text)'}}>{result.image_archetype}</b>{result.image_reason?` — ${result.image_reason}`:''}</>
                :<>No image suggested{result.image_reason?` — ${result.image_reason}`:' — nothing concrete to show'}</>}
            </div>
            {!postImg&&<button style={S.btn('ghost')} onClick={()=>makeImage(result.wants_image?'':'')} disabled={imgBusy}>{imgBusy?'⏳...':result.wants_image?'🖼️ Create image':'🖼️ Create anyway'}</button>}
          </div>
          {!postImg&&<div style={{display:'flex',flexWrap:'wrap',gap:'6px',marginTop:'10px'}}>
            {['social-card','interview-card','code-card','diagram'].map(a=><span key={a} style={S.tag(false)} onClick={()=>makeImage(a)}>{a}</span>)}
          </div>}
          {postImg&&<div style={{marginTop:'10px'}}>
            <img src={postImg.url} alt="" style={{width:'100%',borderRadius:'10px',display:'block'}}/>
            <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginTop:'8px'}}>
              <span style={{fontSize:'11px',color:'var(--text-dim)'}}>{postImg.archetype}{postImg.handle?` · ${postImg.handle}`:''}</span>
              <span style={{display:'flex',gap:'8px'}}>
                <span style={{fontSize:'11px',cursor:'pointer',color:'var(--accent)'}} onClick={()=>makeImage(postImg.archetype)}>Redo</span>
                <span style={{fontSize:'11px',cursor:'pointer',color:'var(--danger)'}} onClick={dropImage}>Remove</span>
              </span>
            </div>
          </div>}
        </div>
        <div style={{display:'flex',gap:'8px',marginTop:'14px',flexWrap:'wrap'}}>
          <button style={S.btn('ghost')} onClick={generate}>🔄 Regenerate</button>
          <button style={S.btn('ghost')} onClick={()=>{navigator.clipboard.writeText(result.content);toast('Copied!')}}>📋 Copy</button>
          {liStatus?.connected&&<button style={{...S.btn('success'),opacity:publishing?0.7:1}} onClick={publish} disabled={publishing}>{publishing?'📤...':'🚀 Publish to LinkedIn'}</button>}
        </div>
      </div>):<Empty icon="✍️" text="Pick a category and generate" sub="AI researches trends, writes in your style, scores the result"/>}
    </div>
  </div>);
}

// ─── 2. Content ──────────────────────────────────────────────────
function ContentTab({config,toast}){
  const [posts,setPosts]=useState([]);const [loading,setLoading]=useState(true);const [filter,setFilter]=useState('all');const [editing,setEditing]=useState(null);const [editContent,setEditContent]=useState('');
  const catMap=Object.fromEntries((config?.categories||[]).map(c=>[c.id,c]));
  const fetch_=useCallback(async()=>{setLoading(true);try{const r=await api.listPosts(filter!=='all'?{status:filter}:{});setPosts(r.posts||[])}catch{}finally{setLoading(false)}},[filter]);
  useEffect(()=>{fetch_()},[fetch_]);
  if(editing)return(<div style={S.card}>
    <div style={{display:'flex',justifyContent:'space-between',marginBottom:'16px'}}><button style={S.btn('ghost')} onClick={()=>setEditing(null)}>← Back</button><span style={S.badge(editing.status==='published'?'#10B981':'#F59E0B')}>{editing.status}</span></div>
    <div style={{fontSize:'18px',fontWeight:700,marginBottom:'16px'}}>{editing.title}</div>
    <textarea style={{...S.textarea,minHeight:'300px'}} value={editContent} onChange={e=>setEditContent(e.target.value)}/>
    <div style={{display:'flex',gap:'8px',marginTop:'14px',flexWrap:'wrap'}}>
      <button style={S.btn()} onClick={async()=>{await api.updatePost(editing.id,{content:editContent});toast('Saved!');fetch_();setEditing(null)}}>💾 Save</button>
      {editing.status==='draft'&&<button style={S.btn('ghost')} onClick={async()=>{await api.updatePost(editing.id,{status:'scheduled',scheduled_date:new Date(Date.now()+172800000).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}),scheduled_time:'9:00 AM'});toast('Scheduled!');fetch_();setEditing(null)}}>📅 Schedule</button>}
      <button style={S.btn('ghost')} onClick={async()=>{try{await api.publishToLinkedIn({post_id:editing.id});toast('Published!');fetch_();setEditing(null)}catch(e){toast(e.message,'error')}}}>🚀 Publish</button>
      <button style={S.btn('danger')} onClick={async()=>{await api.deletePost(editing.id);toast('Deleted');fetch_();setEditing(null)}}>🗑️ Delete</button>
    </div>
  </div>);
  return(<div>
    <div style={{display:'flex',gap:'8px',marginBottom:'16px'}}>{['all','draft','scheduled','published'].map(f=><span key={f} style={S.tag(filter===f)} onClick={()=>setFilter(f)}>{f.charAt(0).toUpperCase()+f.slice(1)}</span>)}</div>
    {loading?<Loader/>:posts.length===0?<Empty icon="📝" text="No posts yet"/>:
    <div style={S.col}>{posts.map(p=>{const c=catMap[p.category];return(<div key={p.id} style={{...S.card,cursor:'pointer'}} onClick={()=>{setEditing(p);setEditContent(p.content)}} onMouseEnter={e=>e.currentTarget.style.borderColor='var(--accent)'} onMouseLeave={e=>e.currentTarget.style.borderColor='var(--border)'}><div style={{display:'flex',justifyContent:'space-between',marginBottom:'6px'}}><span style={{fontSize:'14px',fontWeight:600}}>{c?.icon} {p.title}</span><span style={S.badge(p.status==='published'?'#10B981':p.status==='scheduled'?'#F59E0B':'#71717A')}>{p.status}</span></div><p style={{fontSize:'13px',color:'var(--text-dim)',margin:0,display:'-webkit-box',WebkitLineClamp:2,WebkitBoxOrient:'vertical',overflow:'hidden'}}>{p.content}</p></div>)})}</div>}
  </div>);
}

// ─── 3. Style ────────────────────────────────────────────────────
function StyleTab({config,toast}){
  const [postText,setPostText]=useState('');const [postType,setPostType]=useState('own');const [postCat,setPostCat]=useState('');
  const [stylePosts,setStylePosts]=useState([]);const [counts,setCounts]=useState(null);
  const [profile,setProfile]=useState(null);const [analyzing,setAnalyzing]=useState(false);
  const [viewCat,setViewCat]=useState('');const [viewType,setViewType]=useState('');const [uploading,setUploading]=useState(false);const [recategorizing,setRecategorizing]=useState(false);
  const fileRef=useRef(null);const categories=config?.categories||[];
  const fetch_=useCallback(async()=>{try{const [p,pr,c]=await Promise.all([api.listStylePosts(viewType||viewCat?{...(viewType?{post_type:viewType}:{}),  ...(viewCat?{category:viewCat}:{})}:{}),api.getStyleProfile(),api.getStyleCounts()]);setStylePosts(p.posts||[]);setProfile(pr);setCounts(c)}catch{}},[viewCat,viewType]);
  useEffect(()=>{fetch_()},[fetch_]);
  const addPost=async()=>{if(!postText.trim()){toast('Enter content','error');return}try{const r=await api.addStylePost({content:postText,post_type:postType,category:postCat});toast(r.message||'Added!');setPostText('');fetch_()}catch(e){toast(e.message,'error')}};
  const handleFile=async e=>{const file=e.target.files?.[0];if(!file)return;setUploading(true);try{const r=await api.uploadStyleFile(file,postType,postCat);toast(r.message||`${r.added} imported!`);fetch_()}catch(e){toast(e.message,'error')}finally{setUploading(false);if(fileRef.current)fileRef.current.value=''}};
  const deleteCat=async cat=>{if(!confirm(`Delete all posts in "${cat||'uncategorized'}"?`))return;try{await api.deleteStylePostsBulk({category:cat,...(viewType?{post_type:viewType}:{})});toast('Deleted!');fetch_()}catch(e){toast(e.message,'error')}};
  const deleteAll=async()=>{if(!confirm('Delete ALL style posts?'))return;try{await api.deleteStylePostsBulk({delete_all:'true'});toast('All deleted');fetch_()}catch(e){toast(e.message,'error')}};
  const deleteSingle=async id=>{try{await api.deleteStylePost(id);toast('Removed');fetch_()}catch(e){toast(e.message,'error')}};
  const recategorize=async()=>{setRecategorizing(true);try{const r=await api.recategorizeStylePosts({...(viewType?{post_type:viewType}:{})});toast(r.message||`${r.updated} categorized`);fetch_()}catch(e){toast(e.message,'error')}finally{setRecategorizing(false)}};
  const totalOwn=counts?.total_own||0;const totalInsp=counts?.total_inspiration||0;const totalComment=counts?.total_comment||0;
  const totalUncat=['own','inspiration','comment'].reduce((n,t)=>n+(counts?.[t]?.uncategorized||0),0);

  return(<div style={S.grid2}>
    <div style={S.col}>
      <div style={S.card}><label style={S.label}>Add style content</label>
        <div style={{display:'flex',gap:'8px',marginBottom:'12px'}}>{[{id:'own',l:'My post'},{id:'inspiration',l:'Inspiration'},{id:'comment',l:'My comment style'}].map(t=><span key={t.id} style={S.tag(postType===t.id)} onClick={()=>setPostType(t.id)}>{t.l}</span>)}</div>
        <label style={{...S.label,marginTop:'8px'}}>Category</label>
        <div style={{display:'flex',flexWrap:'wrap',gap:'6px',marginBottom:'12px'}}><span style={S.tag(!postCat,'#71717A')} onClick={()=>setPostCat('')}>🔍 Auto-detect</span>{categories.map(c=><span key={c.id} style={S.tag(postCat===c.id)} onClick={()=>setPostCat(c.id)}>{c.icon} {c.label}</span>)}</div>
        <textarea style={S.textarea} placeholder={postType==='comment'?'Paste your LinkedIn comments...':postType==='inspiration'?'Paste a post you admire...':'Paste your LinkedIn post...'} value={postText} onChange={e=>setPostText(e.target.value)}/>
        <div style={{display:'flex',gap:'8px',marginTop:'10px'}}><button style={{...S.btn('ghost'),flex:1,justifyContent:'center'}} onClick={addPost}>+ Add</button><button style={{...S.btn('ghost'),justifyContent:'center',opacity:uploading?0.7:1}} onClick={()=>fileRef.current?.click()} disabled={uploading}>{uploading?'⏳...':'📁 Upload file'}</button><input ref={fileRef} type="file" accept=".txt,.csv,.json,.pdf" style={{display:'none'}} onChange={handleFile}/></div>
        <div style={{fontSize:'11px',color:'var(--text-dim)',marginTop:'6px'}}>Accepts .txt, .csv, .json, .pdf — split on "Article 1 :" headers, --- separators, post links, or blank lines. Articles spanning several pages stay in one piece.</div>
      </div>
      <div style={S.card}><label style={S.label}>Uploaded content</label>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:'10px'}}>{[{l:'My posts',v:totalOwn,c:'#6366F1'},{l:'Inspiration',v:totalInsp,c:'#F59E0B'},{l:'Comments',v:totalComment,c:'#10B981'}].map((s,i)=><div key={i} style={{textAlign:'center',padding:'12px',borderRadius:'10px',background:'var(--bg-input)'}}><div style={{fontSize:'22px',fontWeight:700,color:s.c}}>{s.v}</div><div style={{fontSize:'11px',color:'var(--text-dim)',marginTop:'2px'}}>{s.l}</div></div>)}</div>
        {totalUncat>0&&<button style={{...S.btn('ghost'),marginTop:'12px',width:'100%',justifyContent:'center',opacity:recategorizing?0.7:1}} onClick={recategorize} disabled={recategorizing}>{recategorizing?'⏳ Categorizing...':`🏷️ Auto-categorize ${totalUncat} uncategorized`}</button>}
        {totalOwn>=2&&<button style={{...S.btn(),marginTop:'14px',width:'100%',justifyContent:'center',opacity:analyzing?0.7:1}} onClick={async()=>{setAnalyzing(true);try{const r=await api.analyzeStyle();setProfile(r);toast('Style analyzed!')}catch(e){toast(e.message,'error')}finally{setAnalyzing(false)}}} disabled={analyzing}>{analyzing?'🔍 Analyzing...':'🎨 Analyze my style'}</button>}
      </div>
      <div style={S.card}><label style={S.label}>Browse & manage</label>
        <div style={{display:'flex',gap:'6px',marginBottom:'10px',flexWrap:'wrap'}}><span style={S.tag(!viewType)} onClick={()=>setViewType('')}>All types</span>{['own','inspiration','comment'].map(t=><span key={t} style={S.tag(viewType===t)} onClick={()=>setViewType(t)}>{t}</span>)}</div>
        <div style={{display:'flex',gap:'6px',marginBottom:'12px',flexWrap:'wrap'}}><span style={S.tag(!viewCat,'#71717A')} onClick={()=>setViewCat('')}>All</span>{categories.map(c=><span key={c.id} style={S.tag(viewCat===c.id)} onClick={()=>setViewCat(c.id)}>{c.icon}</span>)}</div>
        <div style={{maxHeight:'300px',overflowY:'auto',display:'flex',flexDirection:'column',gap:'6px'}}>{stylePosts.length===0?<div style={{color:'var(--text-dim)',fontSize:'13px',textAlign:'center',padding:'20px'}}>No posts match</div>:stylePosts.slice(0,20).map(p=>(<div key={p.id} style={{display:'flex',alignItems:'flex-start',gap:'8px',padding:'8px 10px',borderRadius:'8px',background:'var(--bg-input)',fontSize:'12px'}}><div style={{flex:1,color:'var(--text-muted)',lineHeight:1.4,overflow:'hidden',display:'-webkit-box',WebkitLineClamp:2,WebkitBoxOrient:'vertical'}}>{p.content}</div><div style={{display:'flex',gap:'4px',flexShrink:0,alignItems:'center'}}>{p.category&&<span style={{...S.badge('#71717A'),fontSize:'9px'}}>{p.category}</span>}<button onClick={e=>{e.stopPropagation();deleteSingle(p.id)}} style={{background:'none',border:'none',cursor:'pointer',color:'var(--danger)',fontSize:'14px',padding:'2px'}}>×</button></div></div>))}</div>
        <div style={{display:'flex',gap:'8px',marginTop:'12px'}}>{viewCat&&<button style={S.btn('danger')} onClick={()=>deleteCat(viewCat)}>🗑️ Delete "{viewCat}"</button>}{(totalOwn+totalInsp+totalComment)>0&&<button style={S.btn('danger')} onClick={deleteAll}>🗑️ Delete all</button>}</div>
      </div>
    </div>
    <div style={S.card}><label style={S.label}>Style profile</label>
      {profile?.voice_description?<div style={S.col}>{[{l:'Voice',v:profile.voice_description},{l:'Hook',v:profile.hook_style},{l:'CTA',v:profile.cta_style},{l:'Format',v:profile.formatting_style},{l:'Emoji',v:profile.emoji_style},{l:'Length',v:`${profile.avg_word_count} words`},{l:'Code',v:profile.uses_code_blocks?'Yes':'No'}].filter(s=>s.v&&s.v!=='0 words').map((s,i)=><div key={i} style={{padding:'10px 14px',borderRadius:'8px',background:'var(--bg-input)'}}><div style={{fontSize:'11px',color:'var(--text-dim)',textTransform:'uppercase',letterSpacing:'0.5px'}}>{s.l}</div><div style={{fontSize:'14px',color:'var(--text)',marginTop:'4px',lineHeight:1.5}}>{String(s.v)}</div></div>)}{profile.tone_keywords?.length>0&&<div style={{display:'flex',gap:'6px',flexWrap:'wrap'}}>{profile.tone_keywords.map((k,i)=><span key={i} style={S.tag(true)}>{k}</span>)}</div>}</div>:<Empty icon="🎨" text="Upload 2+ posts, then analyze"/>}
    </div>
  </div>);
}

// ─── 4. Hooks ────────────────────────────────────────────────────
function HooksTab({toast}){const [content,setContent]=useState('');const [hooks,setHooks]=useState([]);const [loading,setLoading]=useState(false);const generate=async()=>{if(!content.trim()){toast('Paste a post','error');return}setLoading(true);setHooks([]);try{const r=await api.generateHooks({content,count:3});setHooks(r.hooks||[]);toast('Hooks generated!')}catch(e){toast(e.message,'error')}finally{setLoading(false)}};return(<div style={S.grid2}><div style={S.col}><div style={S.card}><label style={S.label}>Post content</label><textarea style={{...S.textarea,minHeight:'200px'}} placeholder="Paste the post you want better hooks for..." value={content} onChange={e=>setContent(e.target.value)}/><button style={{...S.btn(),marginTop:'12px',width:'100%',justifyContent:'center',opacity:loading?0.7:1}} onClick={generate} disabled={loading}>{loading?'⏳ Testing...':'🎯 Generate hooks'}</button></div></div><div style={S.col}>{hooks.length>0?hooks.map((h,i)=>(<div key={i} style={{...S.card,borderColor:i===0?'var(--accent)':'var(--border)'}}><div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'10px'}}><span style={S.badge(i===0?'#10B981':'#71717A')}>{i===0?'Best':('#'+(i+1))} · {h.formula?.replace('_',' ')}</span><span style={{fontSize:'20px',fontWeight:700,color:h.predicted_score>=80?'#10B981':h.predicted_score>=60?'#F59E0B':'#EF4444'}}>{h.predicted_score}</span></div><div style={{...S.preview,fontSize:'15px',fontWeight:500,minHeight:'auto',maxHeight:'none'}}>{h.hook}</div><div style={{fontSize:'12px',color:'var(--text-dim)',marginTop:'8px'}}>{h.reasoning}</div><button style={{...S.btn('ghost'),marginTop:'10px'}} onClick={()=>{navigator.clipboard.writeText(h.hook);toast('Copied!')}}>📋 Copy</button></div>)):<Empty icon="🎯" text="Paste a post and test hooks"/>}</div></div>)}

// ─── 5. Carousel ─────────────────────────────────────────────────
function CarouselTab({toast}){const [content,setContent]=useState('');const [slides,setSlides]=useState([]);const [loading,setLoading]=useState(false);const [active,setActive]=useState(0);const generate=async()=>{if(!content.trim()){toast('Paste a post','error');return}setLoading(true);setSlides([]);setActive(0);try{const r=await api.generateCarousel({content,num_slides:8});setSlides(r.slides||[]);toast('Carousel ready!')}catch(e){toast(e.message,'error')}finally{setLoading(false)}};const colors={cover:'#6366F1',content:'#3B82F6',cta:'#10B981'};return(<div style={S.grid2}><div style={S.col}><div style={S.card}><label style={S.label}>Post to convert</label><textarea style={{...S.textarea,minHeight:'200px'}} placeholder="Paste a LinkedIn post..." value={content} onChange={e=>setContent(e.target.value)}/><button style={{...S.btn(),marginTop:'12px',width:'100%',justifyContent:'center',opacity:loading?0.7:1}} onClick={generate} disabled={loading}>{loading?'⏳ Creating...':'📑 Generate carousel'}</button></div></div><div style={S.col}>{slides.length>0?(<><div style={{...S.card,padding:0,overflow:'hidden'}}><div style={{background:colors[slides[active]?.type]||'#3B82F6',padding:'40px 30px',minHeight:'280px',display:'flex',flexDirection:'column',justifyContent:'center',alignItems:'center',textAlign:'center'}}><div style={{fontSize:'10px',fontWeight:600,color:'rgba(255,255,255,0.6)',textTransform:'uppercase',letterSpacing:'1px',marginBottom:'16px'}}>Slide {active+1}/{slides.length} · {slides[active]?.type}</div><div style={{fontSize:'22px',fontWeight:700,color:'#fff',lineHeight:1.3,marginBottom:'14px'}}>{slides[active]?.headline}</div>{slides[active]?.body&&<div style={{fontSize:'15px',color:'rgba(255,255,255,0.85)',lineHeight:1.5}}>{slides[active]?.body}</div>}</div><div style={{display:'flex',justifyContent:'center',gap:'6px',padding:'14px'}}>{slides.map((_,i)=><div key={i} onClick={()=>setActive(i)} style={{width:i===active?'24px':'8px',height:'8px',borderRadius:'4px',background:i===active?'var(--accent)':'var(--border)',cursor:'pointer',transition:'all 0.2s'}}/>)}</div></div></>):<Empty icon="📑" text="Convert a post into carousel slides"/>}</div></div>)}

// ─── 6. Comments ─────────────────────────────────────────────────
function CommentsTab({toast}){const [mode,setMode]=useState('proactive');const [targetPost,setTargetPost]=useState('');const [result,setResult]=useState(null);const [loading,setLoading]=useState(false);const [myPost,setMyPost]=useState('');const [commentText,setCommentText]=useState('');const [name,setName]=useState('');const [reply,setReply]=useState(null);return(<div><div style={{display:'flex',gap:'8px',marginBottom:'20px'}}><span style={S.tag(mode==='proactive','#8B5CF6')} onClick={()=>setMode('proactive')}>💬 Comment on others</span><span style={S.tag(mode==='reply','#10B981')} onClick={()=>setMode('reply')}>↩️ Reply to your comments</span></div>{mode==='proactive'?(<div style={S.grid2}><div style={S.col}><div style={S.card}><label style={S.label}>Post to comment on</label><textarea style={{...S.textarea,minHeight:'180px'}} placeholder="Paste the LinkedIn post..." value={targetPost} onChange={e=>setTargetPost(e.target.value)}/><button style={{...S.btn(),marginTop:'12px',width:'100%',justifyContent:'center',opacity:loading?0.7:1}} onClick={async()=>{if(!targetPost.trim()){toast('Paste a post','error');return}setLoading(true);setResult(null);try{const r=await api.draftProactive({target_post:targetPost});setResult(r);toast('Drafted!')}catch(e){toast(e.message,'error')}finally{setLoading(false)}}} disabled={loading}>{loading?'⏳...':'💬 Draft comment'}</button></div></div><div>{result?(<div style={S.card}><label style={S.label}>Your comment</label><div style={{...S.preview,fontSize:'15px'}}>{result.comment}</div><div style={{fontSize:'12px',color:'var(--text-dim)',marginTop:'10px'}}>{result.strategy}</div><div style={{display:'flex',gap:'8px',marginTop:'12px'}}><button style={S.btn('ghost')} onClick={()=>{navigator.clipboard.writeText(result.comment);toast('Copied!')}}>📋 Copy</button><button style={S.btn('ghost')} onClick={async()=>{setLoading(true);setResult(null);try{const r=await api.draftProactive({target_post:targetPost});setResult(r)}catch(e){toast(e.message,'error')}finally{setLoading(false)}}}>🔄 Try another</button></div></div>):<Empty icon="💬" text="Paste a post to draft a comment"/>}</div></div>):(<div style={S.grid2}><div style={S.col}><div style={S.card}><label style={S.label}>Your post (optional)</label><textarea style={{...S.textarea,minHeight:'60px'}} placeholder="For context..." value={myPost} onChange={e=>setMyPost(e.target.value)}/></div><div style={S.card}><label style={S.label}>Comment to reply to</label><input style={{...S.input,marginBottom:'10px'}} placeholder="Name (optional)" value={name} onChange={e=>setName(e.target.value)}/><textarea style={S.textarea} placeholder="Comment text..." value={commentText} onChange={e=>setCommentText(e.target.value)}/><button style={{...S.btn(),marginTop:'12px',width:'100%',justifyContent:'center',opacity:loading?0.7:1}} onClick={async()=>{if(!commentText.trim()){toast('Enter comment','error');return}setLoading(true);setReply(null);try{const r=await api.draftReply({post_content:myPost,comment_text:commentText,commenter_name:name});setReply(r);toast('Drafted!')}catch(e){toast(e.message,'error')}finally{setLoading(false)}}} disabled={loading}>{loading?'⏳...':'↩️ Draft reply'}</button></div></div><div>{reply?(<div style={S.card}><label style={S.label}>Your reply</label><div style={{...S.preview,fontSize:'15px'}}>{reply.reply}</div><div style={{fontSize:'12px',color:'var(--text-dim)',marginTop:'10px'}}>{reply.strategy}</div><button style={{...S.btn('ghost'),marginTop:'12px'}} onClick={()=>{navigator.clipboard.writeText(reply.reply);toast('Copied!')}}>📋 Copy</button></div>):<Empty icon="↩️" text="Enter a comment to draft a reply"/>}</div></div>)}</div>)}

// ─── 7. Repurpose ────────────────────────────────────────────────
function RepurposeTab({toast}){const [content,setContent]=useState('');const [results,setResults]=useState(null);const [loading,setLoading]=useState(false);const [fmt,setFmt]=useState('twitter_thread');const FMTS=[{id:'twitter_thread',l:'🐦 Twitter'},{id:'newsletter',l:'📰 Newsletter'},{id:'blog_intro',l:'📝 Blog'},{id:'video_script',l:'🎬 Video'}];return(<div style={S.grid2}><div style={S.col}><div style={S.card}><label style={S.label}>Post to repurpose</label><textarea style={{...S.textarea,minHeight:'200px'}} placeholder="Paste your LinkedIn post..." value={content} onChange={e=>setContent(e.target.value)}/><button style={{...S.btn(),marginTop:'12px',width:'100%',justifyContent:'center',opacity:loading?0.7:1}} onClick={async()=>{if(!content.trim()){toast('Paste a post','error');return}setLoading(true);setResults(null);try{const r=await api.repurpose({content});setResults(r.repurposed||{});toast(Object.keys(r.repurposed||{}).length+' formats!')}catch(e){toast(e.message,'error')}finally{setLoading(false)}}} disabled={loading}>{loading?'⏳ Repurposing (~30s)...':'🔄 Repurpose into 4 formats'}</button></div></div><div style={S.col}>{results?(<><div style={{display:'flex',gap:'6px',flexWrap:'wrap'}}>{FMTS.map(f=><span key={f.id} style={S.tag(fmt===f.id)} onClick={()=>setFmt(f.id)}>{f.l}</span>)}</div><div style={S.card}><div style={S.preview}>{results[fmt]||'Not generated.'}</div><button style={{...S.btn('ghost'),marginTop:'12px'}} onClick={()=>{navigator.clipboard.writeText(results[fmt]||'');toast('Copied!')}}>📋 Copy</button></div></>):<Empty icon="🔄" text="1 post → 4 formats"/>}</div></div>)}

// ─── 8. Settings ─────────────────────────────────────────────────
function SettingsTab({config,toast}){
  const [prefs,setPrefs]=useState(null);const [scheduled,setScheduled]=useState([]);const [liStatus,setLiStatus]=useState(null);
  const [selectedModel,setSelectedModel]=useState('');const [customRules,setCustomRules]=useState('');const [rulesSaved,setRulesSaved]=useState(true);
  const DAYS=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];const TIMES=['7:00 AM','8:00 AM','9:00 AM','10:00 AM','12:00 PM','5:00 PM','7:00 PM'];
  const models=config?.models||[];
  const [schedStatus,setSchedStatus]=useState(null);
  const loadSched=useCallback(()=>{api.schedulerStatus().then(setSchedStatus).catch(()=>{})},[]);
  useEffect(()=>{(async()=>{try{const [p,s,li,r]=await Promise.all([api.getPreferences(),api.listPosts({status:'scheduled'}),api.linkedinStatus(),api.getRules()]);setPrefs(p);setScheduled(s.posts||[]);setLiStatus(li);setSelectedModel(p.preferred_model||models[0]?.id||'');setCustomRules(r.rules||'')}catch{}})();loadSched()},[loadSched]);
  const save=async u=>{try{const r=await api.updatePreferences(u);setPrefs(r);loadSched()}catch(e){toast(e.message,'error')}};
  const saveRules=async()=>{try{await api.updateRules(customRules);setRulesSaved(true);toast('Rules saved!')}catch(e){toast(e.message,'error')}};
  if(!prefs)return<Loader/>;
  return(<div style={S.grid2}>
    <div style={S.col}>
      <div style={{...S.card,borderColor:liStatus?.connected?'#10B981':'var(--border)'}}><label style={S.label}>LinkedIn</label>{liStatus?.connected?(<div><div style={{display:'flex',alignItems:'center',gap:'10px'}}><span style={S.badge('#10B981')}>● Connected</span><span style={{fontSize:'14px'}}>{liStatus.name}</span></div>{liStatus.days_remaining&&<div style={{fontSize:'12px',color:'var(--text-dim)',marginTop:'6px'}}>Token: {liStatus.days_remaining} days left {liStatus.auto_refresh?'(auto-refreshes)':''}</div>}</div>):(<div><p style={{fontSize:'13px',color:'var(--text-dim)',margin:'0 0 12px'}}>Connect to enable auto-posting.</p><a href="/api/linkedin/auth" style={{...S.btn(),textDecoration:'none',display:'inline-flex'}}>🔗 Connect LinkedIn</a></div>)}</div>

      <div style={S.card}><label style={S.label}>LLM Model</label><div style={S.col}>{models.map(m=>(<div key={m.id} onClick={async()=>{setSelectedModel(m.id);try{await api.selectModel(m.id);toast(`Model: ${m.name}`)}catch(e){toast(e.message,'error')}}} style={{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'10px 14px',borderRadius:'10px',cursor:'pointer',background:selectedModel===m.id?'var(--accent-bg)':'var(--bg-input)',border:`1px solid ${selectedModel===m.id?'var(--accent)':'var(--border)'}`}}><div><div style={{fontSize:'14px',fontWeight:600,color:selectedModel===m.id?'var(--accent)':'var(--text-muted)'}}>{m.name}</div><div style={{fontSize:'11px',color:'var(--text-dim)',marginTop:'2px'}}>{m.id}</div></div><div style={{display:'flex',gap:'6px',alignItems:'center'}}><span style={S.badge(m.tier==='best'?'#8B5CF6':m.tier==='fast'?'#10B981':m.tier==='free'?'#F59E0B':'#3B82F6')}>{m.tier}</span><span style={{fontSize:'12px',color:'var(--text-dim)'}}>{m.cost}</span></div></div>))}</div></div>

      <div style={S.card}><label style={S.label}>Days</label><div style={{display:'flex',gap:'8px'}}>{DAYS.map(d=><div key={d} onClick={()=>{const days=prefs.preferred_days||[];save({preferred_days:days.includes(d)?days.filter(x=>x!==d):[...days,d]})}} style={{width:'42px',height:'42px',borderRadius:'10px',cursor:'pointer',display:'flex',alignItems:'center',justifyContent:'center',fontSize:'12px',fontWeight:600,background:prefs.preferred_days?.includes(d)?'var(--accent-bg)':'var(--bg-input)',border:`1px solid ${prefs.preferred_days?.includes(d)?'var(--accent)':'var(--border)'}`,color:prefs.preferred_days?.includes(d)?'var(--accent)':'var(--text-dim)'}}>{d}</div>)}</div>
        <div style={{fontSize:'12px',color:'var(--text-dim)',marginTop:'10px'}}>Days set your cadence — {(prefs.preferred_days||[]).length||'no'} post{(prefs.preferred_days||[]).length===1?'':'s'} a week.</div>
      </div>

      <div style={S.card}><label style={S.label}>Weekly cap</label><div style={{display:'flex',alignItems:'center',gap:'16px'}}><input type="range" min="1" max="7" step="1" value={prefs.posting_frequency} onChange={e=>save({posting_frequency:+e.target.value})} style={{flex:1,accentColor:'var(--accent)'}}/><span style={{fontSize:'24px',fontWeight:700,color:'var(--accent)'}}>max {prefs.posting_frequency}</span></div>
        {(prefs.preferred_days||[]).length>prefs.posting_frequency
          ? <div style={{marginTop:'10px',padding:'10px',borderRadius:'8px',background:'var(--accent-bg)',fontSize:'12px',color:'var(--accent)'}}>You've selected {(prefs.preferred_days||[]).length} days but capped at {prefs.posting_frequency}/week — posting stops once the cap is hit, then resets Monday.</div>
          : <div style={{fontSize:'12px',color:'var(--text-dim)',marginTop:'10px'}}>A hard ceiling on autonomous posts per week, counted Monday to Sunday. Your {(prefs.preferred_days||[]).length} selected days sit within it.</div>}
      </div>

      <div style={S.card}><label style={S.label}>Time</label><div style={{display:'flex',flexWrap:'wrap',gap:'8px'}}>{TIMES.map(t=><span key={t} style={S.tag(prefs.preferred_time===t,'#10B981')} onClick={()=>save({preferred_time:t})}>{t}</span>)}</div><div style={{marginTop:'12px',padding:'12px',borderRadius:'10px',background:'var(--success-bg)',fontSize:'13px',color:'var(--success)'}}>🎯 IST: 8-9 AM and 5-7 PM weekdays work best.</div></div>

      <div style={S.card}><div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}><div><div style={{fontSize:'14px',fontWeight:600}}>Autonomous mode</div><div style={{fontSize:'12px',color:'var(--text-dim)',marginTop:'2px'}}>Auto-generate and publish</div></div><div onClick={()=>save({auto_post_enabled:!prefs.auto_post_enabled})} style={{width:'46px',height:'26px',borderRadius:'13px',cursor:'pointer',background:prefs.auto_post_enabled?'var(--accent)':'var(--bg-input)',border:`1px solid ${prefs.auto_post_enabled?'var(--accent)':'var(--border)'}`,position:'relative',flexShrink:0}}><div style={{width:'20px',height:'20px',borderRadius:'10px',background:'#fff',position:'absolute',top:'2px',left:prefs.auto_post_enabled?'23px':'2px',transition:'left 0.2s'}}/></div></div>{prefs.auto_post_enabled?<div style={{marginTop:'10px',padding:'10px',borderRadius:'8px',background:'var(--accent-bg)',fontSize:'12px',color:'var(--accent)'}}>ON — posts auto-generated on your schedule. Turn OFF anytime to pause.</div>:<div style={{marginTop:'10px',padding:'10px',borderRadius:'8px',background:'var(--bg-input)',fontSize:'12px',color:'var(--text-dim)'}}>OFF — generate manually from Generate tab. Turn ON for hands-free posting.</div>}
        {schedStatus&&<div style={{marginTop:'10px',padding:'12px',borderRadius:'8px',background:'var(--bg-input)',border:'1px solid var(--border)',fontSize:'12px'}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:'6px'}}>
            <span style={{fontWeight:600}}>Right now: {schedStatus.should_post?'would post':'would not post'}</span>
            <span style={{cursor:'pointer',color:'var(--accent)',fontSize:'11px'}} onClick={loadSched}>refresh</span>
          </div>
          <div style={{color:'var(--text-dim)',lineHeight:1.6}}>
            <div>{schedStatus.reason}</div>
            {schedStatus.target_time&&<div>Window: {schedStatus.target_time.slice(11,16)} → {schedStatus.catch_up_until?.slice(11,16)} today</div>}
            <div>This week: {schedStatus.published_this_week}/{schedStatus.weekly_cap||'∞'} published</div>
            <div>Background job: {schedStatus.job?.running?`running, next check ${schedStatus.job.next_run?.slice(11,16)||'—'}`:'NOT RUNNING'}</div>
            <div>Last check: {schedStatus.last_tick?.at?`${schedStatus.last_tick.at.slice(11,16)} — ${schedStatus.last_tick.reason}`:'never'}</div>
            {!schedStatus.linkedin_connected&&<div style={{color:'var(--danger)'}}>LinkedIn not connected — posts would save as scheduled, not publish.</div>}
          </div>
        </div>}</div>

      <div style={S.card}><label style={S.label}>Custom rules</label><p style={{fontSize:'13px',color:'var(--text-dim)',margin:'0 0 10px'}}>Strictly followed when generating posts. One rule per line.</p><textarea style={{...S.textarea,minHeight:'120px'}} placeholder={"Example:\n- Never write about building in public\n- Don't mention interview experiences\n- Avoid: synergy, leverage, game-changer\n- Always include code in technical posts"} value={customRules} onChange={e=>{setCustomRules(e.target.value);setRulesSaved(false)}}/><button style={{...S.btn(rulesSaved?'ghost':'primary'),marginTop:'10px',width:'100%',justifyContent:'center'}} onClick={saveRules}>{rulesSaved?'✓ Rules saved':'💾 Save rules'}</button></div>
    </div>

    <div style={S.col}>
      <div style={S.card}><label style={S.label}>Active categories</label><div style={S.col}>{(config?.categories||[]).map(cat=>{const active=prefs.active_categories?.includes(cat.id);return(<div key={cat.id} onClick={()=>{const a=prefs.active_categories||[];save({active_categories:a.includes(cat.id)?a.filter(c=>c!==cat.id):[...a,cat.id]})}} style={{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'10px 14px',borderRadius:'10px',cursor:'pointer',background:active?'var(--accent-bg)':'var(--bg-input)',border:`1px solid ${active?'var(--accent)':'var(--border)'}`}}><span style={{fontSize:'14px',color:active?'var(--accent)':'var(--text-muted)'}}>{cat.icon} {cat.label}</span><div style={{width:'18px',height:'18px',borderRadius:'5px',border:`2px solid ${active?'var(--accent)':'var(--border)'}`,background:active?'var(--accent)':'transparent',display:'flex',alignItems:'center',justifyContent:'center',fontSize:'11px',color:'#fff',flexShrink:0}}>{active&&'✓'}</div></div>)})}</div></div>

      <div style={S.card}><label style={S.label}>Tone per category</label><div style={S.col}>{(config?.categories||[]).filter(c=>prefs.active_categories?.includes(c.id)).map(cat=>(<div key={cat.id} style={{display:'flex',alignItems:'center',gap:'12px',padding:'10px 14px',borderRadius:'10px',background:'var(--bg-input)'}}><span style={{fontSize:'13px',fontWeight:600,minWidth:'160px'}}>{cat.icon} {cat.label}</span><select value={prefs.tone_overrides?.[cat.id]||prefs.default_tone} onChange={e=>{const o={...(prefs.tone_overrides||{}),[cat.id]:e.target.value};save({tone_overrides:o})}} style={{...S.input,width:'auto',padding:'6px 10px',cursor:'pointer',appearance:'auto'}}>{(config?.tones||[]).map(t=><option key={t} value={t}>{t}</option>)}</select></div>))}</div></div>

      <div style={S.card}><label style={S.label}>Scheduled ({scheduled.length})</label>{scheduled.length===0?<div style={{textAlign:'center',padding:'32px',color:'var(--text-dim)',fontSize:'13px'}}>None</div>:<div style={S.col}>{scheduled.map(p=>(<div key={p.id} style={{padding:'12px',borderRadius:'10px',background:'var(--bg-input)',border:'1px solid var(--border)'}}><div style={{fontSize:'14px',fontWeight:600}}>{p.title}</div><div style={{fontSize:'12px',color:'var(--text-dim)',marginTop:'4px'}}>📅 {p.scheduled_date} {p.scheduled_time}</div></div>))}</div>}</div>
    </div>
  </div>);
}

// ─── Images ──────────────────────────────────────────────────────
function ImagesTab({toast}){
  const [identity,setIdentity]=useState(null);const [handles,setHandles]=useState([]);
  const [presets,setPresets]=useState([]);const [imgCfg,setImgCfg]=useState(null);
  const [newHandle,setNewHandle]=useState('');const [busy,setBusy]=useState('');
  const [testArch,setTestArch]=useState('social-card');const [testText,setTestText]=useState('');
  const [testImg,setTestImg]=useState(null);
  const avatarRef=useRef(null);const inspoRef=useRef(null);

  const fetch_=useCallback(async()=>{try{const [i,p,c]=await Promise.all([api.getImageIdentity(),api.listImagePresets(),api.getImageConfig()]);setIdentity(i.identity);setHandles(i.handles||[]);setPresets(p.presets||[]);setImgCfg(c)}catch(e){toast(e.message,'error')}},[toast]);
  useEffect(()=>{fetch_()},[fetch_]);

  const saveIdentity=async(patch)=>{try{const r=await api.updateImageIdentity(patch);setIdentity({...r,avatar_url:identity?.avatar_url||''});toast('Saved')}catch(e){toast(e.message,'error')}};
  const onAvatar=async e=>{const f=e.target.files?.[0];if(!f)return;setBusy('avatar');try{await api.uploadAvatar(f);toast('Photo updated');fetch_()}catch(e){toast(e.message,'error')}finally{setBusy('');if(avatarRef.current)avatarRef.current.value=''}};
  const onInspo=async e=>{const files=Array.from(e.target.files||[]);if(!files.length)return;setBusy('inspo');let ok=0;
    for(const f of files){try{const r=await api.uploadInspirationImage(f);ok++;if(r.warning)toast(r.warning,'error')}catch(err){toast(`${f.name}: ${err.message}`,'error')}}
    toast(`${ok} of ${files.length} analyzed`);setBusy('');if(inspoRef.current)inspoRef.current.value='';fetch_()};
  const addHandle=async()=>{if(!newHandle.trim())return;try{const r=await api.addImageHandle(newHandle.trim());toast(r.message);setNewHandle('');fetch_()}catch(e){toast(e.message,'error')}};
  const seed=async()=>{try{const r=await api.seedImageHandles();toast(r.message);fetch_()}catch(e){toast(e.message,'error')}};
  const delHandle=async id=>{try{await api.deleteImageHandle(id);fetch_()}catch(e){toast(e.message,'error')}};
  const toggleHandle=async(id,en)=>{try{await api.toggleImageHandle(id,en);fetch_()}catch(e){toast(e.message,'error')}};
  const delPreset=async id=>{if(!confirm('Delete this style preset?'))return;try{await api.deleteImagePreset(id);toast('Deleted');fetch_()}catch(e){toast(e.message,'error')}};
  const runTest=async()=>{if(!testText.trim()){toast('Paste a post to preview','error');return}setBusy('test');setTestImg(null);
    try{const r=await api.generatePostImage({content:testText,archetype:testArch});
      if(!r.generated){toast(r.message);}else{setTestImg(r);toast(`${r.archetype} rendered`)}}
    catch(e){toast(e.message,'error')}finally{setBusy('')}};

  const archetypes=imgCfg?.archetypes||[];
  return(<div style={S.grid2}>
    <div style={S.col}>
      <div style={S.card}><label style={S.label}>Card identity</label>
        <div style={{display:'flex',gap:'14px',alignItems:'center',marginBottom:'14px'}}>
          {identity?.avatar_url
            ? <img src={identity.avatar_url} alt="" style={{width:'62px',height:'62px',borderRadius:'50%',objectFit:'cover'}}/>
            : <div style={{width:'62px',height:'62px',borderRadius:'50%',background:'var(--bg-input)',display:'flex',alignItems:'center',justifyContent:'center',fontSize:'20px',color:'var(--text-dim)'}}>👤</div>}
          <button style={S.btn('ghost')} onClick={()=>avatarRef.current?.click()} disabled={busy==='avatar'}>{busy==='avatar'?'⏳...':'Upload photo'}</button>
          <input ref={avatarRef} type="file" accept="image/*" style={{display:'none'}} onChange={onAvatar}/>
        </div>
        <label style={S.label}>Display name</label>
        <input style={S.input} value={identity?.display_name||''} placeholder="Sumeet Basu"
          onChange={e=>setIdentity({...identity,display_name:e.target.value})}
          onBlur={e=>saveIdentity({display_name:e.target.value})}/>
        <label style={{...S.label,marginTop:'12px'}}>Headline (optional)</label>
        <input style={S.input} value={identity?.headline||''} placeholder="Senior Software Engineer"
          onChange={e=>setIdentity({...identity,headline:e.target.value})}
          onBlur={e=>saveIdentity({headline:e.target.value})}/>
        <div style={{display:'flex',gap:'8px',marginTop:'14px',flexWrap:'wrap'}}>
          <span style={S.tag(identity?.verified)} onClick={()=>saveIdentity({verified:!identity?.verified})}>
            {identity?.verified?'✓ Badge on':'Badge off'}</span>
          {['round-robin','random'].map(s=><span key={s} style={S.tag(identity?.handle_strategy===s)} onClick={()=>saveIdentity({handle_strategy:s})}>{s}</span>)}
        </div>
        <div style={{fontSize:'11px',color:'var(--text-dim)',marginTop:'8px'}}>The badge sits next to your real name on a joke handle, so it reads as a verified account that doesn't exist. Off is the safer default.</div>
      </div>

      <div style={S.card}><label style={S.label}>Handle pool ({handles.filter(h=>h.enabled).length} active)</label>
        <div style={{display:'flex',gap:'8px',marginBottom:'12px'}}>
          <input style={S.input} value={newHandle} placeholder="@BugWhisperer" onChange={e=>setNewHandle(e.target.value)} onKeyDown={e=>e.key==='Enter'&&addHandle()}/>
          <button style={S.btn('ghost')} onClick={addHandle}>+ Add</button>
        </div>
        {!handles.length&&<button style={{...S.btn('ghost'),width:'100%',justifyContent:'center'}} onClick={seed}>Add the starter handles</button>}
        <div style={{display:'flex',flexDirection:'column',gap:'6px'}}>
          {handles.map(h=><div key={h.id} style={{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'8px 12px',borderRadius:'8px',background:'var(--bg-input)',opacity:h.enabled?1:0.45}}>
            <span style={{fontSize:'13px'}}>{h.handle}</span>
            <span style={{display:'flex',alignItems:'center',gap:'10px'}}>
              <span style={{fontSize:'11px',color:'var(--text-dim)'}}>used {h.use_count}×</span>
              <span style={{cursor:'pointer',fontSize:'12px'}} onClick={()=>toggleHandle(h.id,!h.enabled)}>{h.enabled?'⏸':'▶'}</span>
              <span style={{cursor:'pointer',color:'var(--danger)'}} onClick={()=>delHandle(h.id)}>✕</span>
            </span>
          </div>)}
        </div>
      </div>
    </div>

    <div style={S.col}>
      <div style={S.card}><label style={S.label}>Inspiration styles ({presets.length})</label>
        <button style={{...S.btn('ghost'),width:'100%',justifyContent:'center',marginBottom:'10px'}} onClick={()=>inspoRef.current?.click()} disabled={busy==='inspo'}>{busy==='inspo'?'⏳ Analyzing...':'📁 Upload inspiration images'}</button>
        <input ref={inspoRef} type="file" accept="image/*" multiple style={{display:'none'}} onChange={onInspo}/>
        <div style={{fontSize:'11px',color:'var(--text-dim)',marginBottom:'12px'}}>Each image is read once to extract its palette, emphasis style and layout, then saved as a reusable preset. Nothing is trained — generation reads the preset, not the image.</div>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'10px'}}>
          {presets.map(p=><div key={p.id} style={{borderRadius:'10px',overflow:'hidden',border:'1px solid var(--border)',background:'var(--bg-input)'}}>
            {p.source_url&&<img src={p.source_url} alt="" style={{width:'100%',height:'96px',objectFit:'cover',display:'block'}}/>}
            <div style={{padding:'8px 10px'}}>
              <div style={{fontSize:'12px',fontWeight:600,marginBottom:'4px'}}>{p.name||p.archetype}</div>
              <div style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}>
                <span style={S.badge('#6366F1')}>{p.archetype}</span>
                <span style={{display:'flex',alignItems:'center',gap:'6px'}}>
                  <span style={{width:'14px',height:'14px',borderRadius:'4px',background:p.style?.accent_color||'#999',display:'inline-block'}}/>
                  <span style={{cursor:'pointer',color:'var(--danger)',fontSize:'12px'}} onClick={()=>delPreset(p.id)}>✕</span>
                </span>
              </div>
            </div>
          </div>)}
        </div>
        {!presets.length&&<div style={{fontSize:'12px',color:'var(--text-dim)',textAlign:'center',padding:'14px 0'}}>No presets yet — built-in defaults will be used.</div>}
      </div>

      <div style={S.card}><label style={S.label}>Preview a card</label>
        <div style={{display:'flex',flexWrap:'wrap',gap:'6px',marginBottom:'10px'}}>
          <span style={S.tag(!testArch,'#71717A')} onClick={()=>setTestArch('')}>🔍 Let AI choose</span>
          {archetypes.map(a=><span key={a.id} style={S.tag(testArch===a.id)} onClick={()=>setTestArch(a.id)} title={a.description}>{a.label}</span>)}
        </div>
        <textarea style={{...S.textarea,minHeight:'90px'}} placeholder="Paste a post to see the image it would get..." value={testText} onChange={e=>setTestText(e.target.value)}/>
        <button style={{...S.btn(),width:'100%',justifyContent:'center',marginTop:'10px'}} onClick={runTest} disabled={busy==='test'}>{busy==='test'?'⏳ Rendering...':'🖼️ Generate preview'}</button>
        {testImg&&<div style={{marginTop:'12px'}}>
          <img src={testImg.url} alt="" style={{width:'100%',borderRadius:'10px',display:'block'}}/>
          <div style={{fontSize:'11px',color:'var(--text-dim)',marginTop:'6px'}}>{testImg.archetype}{testImg.handle?` · ${testImg.handle}`:''}{testImg.reason?` · ${testImg.reason}`:''}</div>
        </div>}
      </div>
    </div>
  </div>);
}

// ─── Main (state persisted across tabs) ──────────────────────────
export default function App(){
  // Read initial tab from URL hash (e.g. #settings, #content)
  const getTabFromHash = () => {
    const hash = window.location.hash.replace('#','').split('?')[0];
    const valid = ['generate','content','style','images','hooks','carousel','comments','repurpose','settings'];
    return valid.includes(hash) ? hash : 'generate';
  };
  const [tab,setTab]=useState(getTabFromHash);
  const [config,setConfig]=useState(null);const [connected,setConnected]=useState(null);const [td,setTd]=useState(null);
  const [genState,setGenState]=useState({cat:'',topic:'',fmt:'story',tone:'Conversational',result:null});
  const toast=useCallback((m,t='success')=>setTd({msg:m,type:t}),[]);

  // Persist tab in URL hash
  const switchTab = useCallback((id) => {
    setTab(id);
    window.location.hash = id;
  }, []);

  // Listen for browser back/forward
  useEffect(() => {
    const onHash = () => setTab(getTabFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  // Check for LinkedIn callback params in hash
  useEffect(() => {
    const hash = window.location.hash;
    if (hash.includes('linkedin=connected')) {
      toast('LinkedIn connected successfully!');
      window.location.hash = 'settings';
    } else if (hash.includes('linkedin_error=')) {
      const err = new URLSearchParams(hash.split('?')[1] || '').get('linkedin_error');
      toast(`LinkedIn error: ${err}`, 'error');
      window.location.hash = 'settings';
    }
  }, []);

  useEffect(()=>{(async()=>{try{await api.health();setConfig(await api.getConfig());setConnected(true)}catch{setConnected(false)}})()},[]);
  const tabs=[{id:'generate',l:'✨ Generate'},{id:'content',l:'📝 Content'},{id:'style',l:'🎨 Style'},{id:'images',l:'🖼️ Images'},{id:'hooks',l:'🎯 Hooks'},{id:'carousel',l:'📑 Carousel'},{id:'comments',l:'💬 Comments'},{id:'repurpose',l:'🔄 Repurpose'},{id:'settings',l:'⚙️ Settings'}];
  return(<div style={{fontFamily:font,minHeight:'100vh',background:'var(--bg)',color:'var(--text)'}}>
    <header style={{maxWidth:'1200px',margin:'0 auto',padding:'20px 24px 16px',display:'flex',alignItems:'center',justifyContent:'space-between',borderBottom:'1px solid var(--border)',flexWrap:'wrap',gap:'12px'}}><div style={{display:'flex',alignItems:'center',gap:'12px'}}><div style={{width:'36px',height:'36px',borderRadius:'10px',background:'var(--accent)',display:'flex',alignItems:'center',justifyContent:'center',fontSize:'16px',fontWeight:700,color:'#fff'}}>LP</div><div><div style={{fontSize:'17px',fontWeight:700,letterSpacing:'-0.3px'}}>LinkedIn Post Generator</div><div style={{fontSize:'11px',color:'var(--text-dim)'}}>{connected===true&&<span style={{color:'var(--success)'}}>● Connected</span>}{connected===false&&<span style={{color:'var(--danger)'}}>● Backend offline</span>}</div></div></div><nav style={{display:'flex',gap:'3px',background:'var(--bg-input)',borderRadius:'10px',padding:'3px',flexWrap:'wrap'}}>{tabs.map(t=><button key={t.id} onClick={()=>switchTab(t.id)} style={{padding:'6px 12px',borderRadius:'8px',border:'none',cursor:'pointer',fontSize:'12px',fontWeight:500,fontFamily:font,background:tab===t.id?'var(--accent-bg)':'transparent',color:tab===t.id?'var(--accent)':'var(--text-muted)',whiteSpace:'nowrap'}}>{t.l}</button>)}</nav></header>
    <main style={{maxWidth:'1200px',margin:'0 auto',padding:'24px'}}>{connected===false?(<div style={{...S.card,textAlign:'center',padding:'60px 24px'}}><div style={{fontSize:'48px',marginBottom:'16px'}}>🔌</div><div style={{fontSize:'18px',fontWeight:600,marginBottom:'8px'}}>Backend not running</div><pre style={{background:'var(--bg-input)',padding:'14px',borderRadius:'10px',marginTop:'12px',fontSize:'13px',textAlign:'left',border:'1px solid var(--border)',overflow:'auto',display:'inline-block'}}>{`cd backend\npip install -r requirements.txt\ncp .env.example .env\npython -m uvicorn api.main:app --reload`}</pre></div>):connected===null?<Loader text="Connecting..."/>:<>
      {tab==='generate'&&<GenerateTab config={config} toast={toast} genState={genState} setGenState={setGenState}/>}
      {tab==='content'&&<ContentTab config={config} toast={toast}/>}
      {tab==='style'&&<StyleTab config={config} toast={toast}/>}
      {tab==='images'&&<ImagesTab toast={toast}/>}
      {tab==='hooks'&&<HooksTab toast={toast}/>}
      {tab==='carousel'&&<CarouselTab toast={toast}/>}
      {tab==='comments'&&<CommentsTab toast={toast}/>}
      {tab==='repurpose'&&<RepurposeTab toast={toast}/>}
      {tab==='settings'&&<SettingsTab config={config} toast={toast}/>}
    </>}</main>
    {td&&<Toast msg={td.msg} type={td.type} onClose={()=>setTd(null)}/>}
    <style>{`@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&display=swap');:root{--bg:#fafaf9;--bg-card:#fff;--bg-input:#f5f5f4;--border:#e7e5e4;--text:#1c1917;--text-muted:#57534e;--text-dim:#a8a29e;--accent:#6366f1;--accent-bg:rgba(99,102,241,0.08);--success:#16a34a;--success-bg:rgba(22,163,74,0.08);--danger:#dc2626;--danger-bg:rgba(220,38,38,0.08)}@media(prefers-color-scheme:dark){:root{--bg:#0c0a09;--bg-card:#1c1917;--bg-input:#292524;--border:#44403c;--text:#fafaf9;--text-muted:#a8a29e;--text-dim:#78716c;--accent:#818cf8;--accent-bg:rgba(129,140,248,0.12);--success:#4ade80;--success-bg:rgba(74,222,128,0.1);--danger:#f87171;--danger-bg:rgba(248,113,113,0.1)}}*{box-sizing:border-box;margin:0;padding:0}body{background:var(--bg)}::selection{background:var(--accent);color:#fff}input:focus,textarea:focus,select:focus{border-color:var(--accent)!important;outline:none}@keyframes slideIn{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}`}</style>
  </div>);
}
