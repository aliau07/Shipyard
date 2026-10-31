import React, { useState } from 'react';
import { postComment } from '../api';
import { STATUS_LABELS, errorMessages, formatDateTime } from '../format';
import Icon from './Icon';

const EVENT_ICONS = {
  created: 'file-text', updated: 'pencil', change_added: 'plus', change_removed: 'x', submitted: 'search-check',
  signed_off: 'badge-check', changes_requested: 'undo-2', approved: 'check', started: 'circle-play',
  released: 'circle-check', blocked: 'ban', unblocked: 'circle-play', cancelled: 'circle-slash', reopened: 'rotate-ccw',
  commented: 'message-square',
};

const MAX_SCREENSHOTS = 5;

function Screenshots({ items }) {
  const [open, setOpen] = useState(null);
  if (!items || items.length === 0) return null;
  return (
    <>
      <div className="photo-grid screenshots">
        {items.map((shot, index) => (
          <button key={shot.id} type="button" className="photo thumb" onClick={() => setOpen(shot)} aria-label={`Open screenshot ${index + 1}`}>
            <img src={shot.thumbnail} alt={`Screenshot ${index + 1}`} loading="lazy" />
          </button>
        ))}
      </div>
      {open && (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label="Screenshot" onClick={() => setOpen(null)}>
          <figure onClick={event => event.stopPropagation()}>
            <img src={open.image} alt="Screenshot" />
            <figcaption><span className="actions"><button type="button" className="secondary small" onClick={() => setOpen(null)}>Close</button></span></figcaption>
          </figure>
        </div>
      )}
    </>
  );
}

function statusChange(item) {
  if (!item.from_status || !item.to_status || item.from_status === item.to_status) return null;
  return `${STATUS_LABELS[item.from_status] ?? item.from_status} → ${STATUS_LABELS[item.to_status] ?? item.to_status}`;
}

export function Timeline({ items }) {
  const visible = items.filter(item => item.type === 'comment' || item.kind !== 'commented');
  return (
    <ol className="timeline">
      {visible.map(item => {
        const isComment = item.type === 'comment';
        const change = isComment ? null : statusChange(item);
        return (
          <li key={`${item.type}${item.id}`} className={`timeline-item ${item.kind === 'blocked' ? 'flagged' : ''}`}>
            <span className="timeline-dot" aria-hidden="true">
              <Icon name={isComment ? 'message-square' : EVENT_ICONS[item.kind] ?? 'info'} size={14} />
            </span>
            <div className="timeline-body">
              <div className="timeline-head">
                <strong>{isComment ? 'Comment' : item.kind_display}</strong>
                {change && <span className="muted small">{change}</span>}
              </div>
              <div className="muted small">{isComment ? item.author_name : item.actor_name} · {formatDateTime(item.created_at)}</div>
              {isComment
                ? <><p className="prewrap comment-text">{item.body}</p><Screenshots items={item.screenshots} /></>
                : item.message && <p className="prewrap event-message">{item.message}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function CommentForm({ release, onPosted }) {
  const [body, setBody] = useState('');
  const [files, setFiles] = useState([]);
  const [errors, setErrors] = useState([]);
  const [saving, setSaving] = useState(false);

  function pick(event) {
    const chosen = Array.from(event.target.files || []);
    event.target.value = '';
    const images = [];
    const problems = [];
    for (const file of chosen) {
      if (/^image\/(png|jpeg|webp)$/.test(file.type)) images.push(file);
      else problems.push(`"${file.name}" is not a PNG, JPEG or WebP image.`);
    }
    const combined = files.concat(images);
    if (combined.length > MAX_SCREENSHOTS) problems.push(`Attach up to ${MAX_SCREENSHOTS} screenshots.`);
    setFiles(combined.slice(0, MAX_SCREENSHOTS));
    setErrors(problems);
  }

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setErrors([]);
    try {
      await postComment(release.id, body, files);
      setBody('');
      setFiles([]);
      onPosted();
    } catch (error) {
      setErrors(errorMessages(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="comment-form" onSubmit={submit}>
      <label htmlFor="comment-body" className="label">Add a comment</label>
      <textarea id="comment-body" rows={3} value={body} onChange={e => setBody(e.target.value)} required
                placeholder="Test results, rollout notes, questions for the component owners..." />
      <div className="actions">
        <button type="submit" className="secondary" disabled={saving || !body.trim()}>{saving ? 'Posting...' : 'Post comment'}</button>
        <label className="file-pick inline">
          <input type="file" accept="image/png,image/jpeg,image/webp" multiple onChange={pick} aria-label="Attach screenshots" />
          <span className="button secondary small"><Icon name="camera" />Attach screenshots</span>
        </label>
        {files.length > 0 && (
          <span className="tags">
            {files.map((file, index) => (
              <span key={`${file.name}${index}`} className="tag">{file.name}
                <button type="button" className="link" aria-label={`Remove ${file.name}`}
                        onClick={() => setFiles(files.filter((_, i) => i !== index))}>×</button>
              </span>
            ))}
          </span>
        )}
      </div>
      {errors.map(message => <p key={message} className="error" role="alert">{message}</p>)}
    </form>
  );
}
