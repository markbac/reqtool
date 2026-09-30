import { useState, useEffect, useRef } from 'react';
import { useApp } from '../../AppContext';
import { api } from '../../api';

export function DiscussionSection({ uid, currentUser = 'user' }) {
  const { toast } = useApp();
  const [comments, setComments] = useState([]);
  const [newText, setNewText] = useState('');
  const [replyTo, setReplyTo] = useState(null);
  const [editingUid, setEditingUid] = useState(null);
  const [editText, setEditText] = useState('');
  const [showResolved, setShowResolved] = useState(false);
  const textareaRef = useRef(null);

  const load = () => api.comments.list(uid).then(setComments).catch(() => {});
  useEffect(() => { load(); }, [uid]);

  const handlePost = async () => {
    const text = newText.trim();
    if (!text) return;
    try {
      await api.comments.add(uid, { text, author: currentUser, reply_to: replyTo });
      setNewText(''); setReplyTo(null);
      load();
    } catch (err) { toast(err.message, 'error'); }
  };

  const handleEdit = async (commentUid) => {
    try {
      await api.comments.update(uid, commentUid, { text: editText });
      setEditingUid(null); setEditText('');
      load();
    } catch (err) { toast(err.message, 'error'); }
  };

  const handleResolve = async (commentUid, resolved) => {
    try {
      await api.comments.resolve(uid, commentUid, resolved);
      load();
    } catch (err) { toast(err.message, 'error'); }
  };

  const handleDelete = async (commentUid) => {
    try {
      await api.comments.delete(uid, commentUid);
      load();
    } catch (err) { toast(err.message, 'error'); }
  };

  const topLevel = comments.filter(c => !c.reply_to);
  const repliesTo = (parentUid) => comments.filter(c => c.reply_to === parentUid);
  const visible = showResolved ? topLevel : topLevel.filter(c => !c.resolved);
  const resolvedCount = topLevel.filter(c => c.resolved).length;

  const CommentNode = ({ comment, depth = 0 }) => (
    <div className={`comment-node ${comment.resolved ? 'comment-node--resolved' : ''}`}
         style={{ marginLeft: depth * 20 }}>
      <div className="comment-header">
        <span className="comment-author">{comment.author}</span>
        <span className="comment-date">{comment.created_at?.slice(0,10)}</span>
        {comment.updated_at && <span className="comment-edited text-muted">(edited)</span>}
        {comment.resolved && <span className="comment-resolved-badge">resolved</span>}
      </div>
      {editingUid === comment.uid ? (
        <div className="comment-edit-form">
          <textarea value={editText} onChange={e => setEditText(e.target.value)} rows={3} />
          <div className="comment-edit-actions">
            <button className="btn btn-primary" style={{ fontSize: 11 }} onClick={() => handleEdit(comment.uid)}>Save</button>
            <button className="btn btn-ghost" style={{ fontSize: 11 }} onClick={() => setEditingUid(null)}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="comment-body">{comment.text}</div>
      )}
      <div className="comment-actions">
        <button className="comment-action-btn" onClick={() => { setReplyTo(comment.uid); textareaRef.current?.focus(); }}>↩ Reply</button>
        {comment.author === currentUser && (
          <button className="comment-action-btn" onClick={() => { setEditingUid(comment.uid); setEditText(comment.text); }}>Edit</button>
        )}
        <button className="comment-action-btn" onClick={() => handleResolve(comment.uid, !comment.resolved)}>
          {comment.resolved ? 'Reopen' : '✓ Resolve'}
        </button>
        {comment.author === currentUser && (
          <button className="comment-action-btn comment-action-btn--danger" onClick={() => handleDelete(comment.uid)}>Delete</button>
        )}
      </div>
      {repliesTo(comment.uid).map(r => <CommentNode key={r.uid} comment={r} depth={depth + 1} />)}
    </div>
  );

  return (
    <div className="discussion-section">
      {resolvedCount > 0 && (
        <button className="btn btn-ghost" style={{ fontSize: 11, marginBottom: 8 }}
          onClick={() => setShowResolved(v => !v)}>
          {showResolved ? 'Hide' : 'Show'} {resolvedCount} resolved
        </button>
      )}

      {visible.length === 0 && !replyTo && (
        <div className="discussion-empty">No comments yet. Add the first one below.</div>
      )}

      {visible.map(c => <CommentNode key={c.uid} comment={c} />)}

      <div className="discussion-compose">
        {replyTo && (
          <div className="reply-indicator">
            Replying to thread
            <button className="btn btn-ghost" style={{ fontSize: 10 }} onClick={() => setReplyTo(null)}>✕</button>
          </div>
        )}
        <textarea
          ref={textareaRef}
          value={newText}
          onChange={e => setNewText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handlePost(); }}
          placeholder={replyTo ? "Write a reply... (Ctrl+Enter to post)" : "Add a comment... (Ctrl+Enter to post)"}
          rows={3}
        />
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
          <button className="btn btn-primary" style={{ fontSize: 12 }} onClick={handlePost} disabled={!newText.trim()}>
            {replyTo ? 'Reply' : 'Comment'}
          </button>
        </div>
      </div>
    </div>
  );
}
