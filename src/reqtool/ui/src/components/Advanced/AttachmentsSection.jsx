import { useState, useEffect, useRef } from 'react';
import { useApp } from '../../AppContext';
import { api } from '../../api';

function getFileIcon(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  const icons = { pdf: '📄', png: '🖼', jpg: '🖼', jpeg: '🖼', gif: '🖼', svg: '🖼',
                  docx: '📝', doc: '📝', xlsx: '📊', xls: '📊', csv: '📊',
                  md: '📋', txt: '📋', yaml: '⚙', json: '⚙', zip: '📦', tar: '📦' };
  return icons[ext] || '📎';
}

export function AttachmentsSection({ uid }) {
  const { toast } = useApp();
  const [attachments, setAttachments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  const load = () => {
    api.attachments.list(uid).then(setAttachments).catch(() => {});
  };
  useEffect(() => { load(); }, [uid]);

  const handleFiles = async (files) => {
    setUploading(true);
    for (const file of files) {
      try {
        await api.attachments.upload(uid, file.name, file);
        toast(`Uploaded: ${file.name}`, 'success', 2000);
      } catch (err) { toast(`Upload failed: ${err.message}`, 'error'); }
    }
    setUploading(false);
    load();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    handleFiles([...e.dataTransfer.files]);
  };

  const handleDelete = async (filename) => {
    if (!confirm(`Delete attachment '${filename}'?`)) return;
    try {
      await api.attachments.delete(uid, filename);
      toast('Deleted', 'info', 1500);
      load();
    } catch (err) { toast(err.message, 'error'); }
  };

  const fmtSize = (bytes) => bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes/1024).toFixed(1)} KB` : `${(bytes/1048576).toFixed(1)} MB`;

  return (
    <div className="attachments-section">
      {attachments.length > 0 && (
        <div className="attachment-list">
          {attachments.map(a => {
            const isImage = /\.(png|jpe?g|gif|svg|webp)$/i.test(a.filename);
            const downloadUrl = api.attachments.download(uid, a.filename);
            const copyImgMarkdown = () => {
              navigator.clipboard.writeText(`![${a.filename}](${downloadUrl})`);
              toast('Copied image markdown snippet!', 'success', 2000);
            };
            return (
              <div key={a.filename} className="attachment-item" style={{ flexDirection: isImage ? 'column' : 'row', alignItems: isImage ? 'flex-start' : 'center', gap: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, width: '100%' }}>
                  <span className="attachment-icon">{getFileIcon(a.filename)}</span>
                  <a
                    href={downloadUrl}
                    target="_blank" rel="noopener noreferrer"
                    className="attachment-name"
                  >{a.filename}</a>
                  <span className="attachment-meta">{fmtSize(a.size_bytes)}</span>
                  {isImage && (
                    <button
                      className="btn btn-ghost"
                      style={{ fontSize: 10, padding: '2px 6px', marginLeft: 'auto' }}
                      onClick={copyImgMarkdown}
                      title="Copy inline markdown image snippet"
                    >🖼 Copy Markdown</button>
                  )}
                  <button className="string-list-remove" onClick={() => handleDelete(a.filename)} title="Delete attachment">✕</button>
                </div>
                {isImage && (
                  <div style={{ marginTop: 4, width: '100%', maxHeight: 180, overflow: 'hidden', borderRadius: 4, border: '1px solid var(--border-color)', background: '#000' }}>
                    <img src={downloadUrl} alt={a.filename} style={{ maxWidth: '100%', maxHeight: 180, objectFit: 'contain', display: 'block' }} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      <div
        className={`attachment-dropzone ${uploading ? 'attachment-dropzone--uploading' : ''}`}
        onDragOver={e => e.preventDefault()}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        {uploading ? <span className="spinner" /> : <span>↑ Drop files here or click to upload</span>}
        <input
          ref={fileInputRef} type="file" multiple style={{ display: 'none' }}
          onChange={e => handleFiles([...e.target.files])}
        />
      </div>
    </div>
  );
}
