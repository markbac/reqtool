/**
 * IterationsPanel.jsx -- Iteration, Sprint, Phase & Milestone Manager.
 * Flexible methodology support: Scrum, Waterfall, Wagile (hybrid), and Kanban.
 */

import { useState, useEffect } from 'react';
import { useApp } from '../AppContext';
import { api } from '../api';

export function IterationsPanel({ onClose }) {
  const { toast } = useApp();
  const [iterations, setIterations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedIt, setSelectedIt] = useState(null);
  const [metrics, setMetrics] = useState(null);

  const [id, setId] = useState('');
  const [title, setTitle] = useState('');
  const [methodology, setMethodology] = useState('scrum');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [milestoneDate, setMilestoneDate] = useState('');
  const [capacity, setCapacity] = useState('40');
  const [status, setStatus] = useState('planned');
  const [notes, setNotes] = useState('');

  const loadAll = async () => {
    setLoading(true);
    try {
      const data = await api.iterations.list();
      setIterations(data);
      if (data.length > 0 && !selectedIt) {
        handleSelect(data[0]);
      }
    } catch (err) {
      toast.error('Failed to load iterations: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleSelect = async (it) => {
    setSelectedIt(it);
    setId(it.id);
    setTitle(it.title || '');
    setMethodology(it.methodology || 'scrum');
    setStartDate(it.start_date || '');
    setEndDate(it.end_date || '');
    setMilestoneDate(it.milestone_date || '');
    setCapacity(String(it.capacity_story_points || 40));
    setStatus(it.status || 'planned');
    setNotes(it.notes || '');

    try {
      const m = await api.iterations.metrics(it.id);
      setMetrics(m);
    } catch {
      setMetrics(null);
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (!id.trim() || !title.trim()) return;
    try {
      await api.iterations.create({
        id: id.trim(),
        title: title.trim(),
        methodology,
        start_date: startDate || null,
        end_date: endDate || null,
        milestone_date: milestoneDate || null,
        capacity_story_points: parseFloat(capacity) || 0,
        status,
        notes,
      });
      toast.success(`Saved iteration '${id.trim()}'`);
      await loadAll();
    } catch (err) {
      toast.error('Failed to save iteration: ' + err.message);
    }
  };

  const handleDelete = async (itId) => {
    if (!confirm(`Delete iteration '${itId}'?`)) return;
    try {
      await api.iterations.delete(itId);
      toast.success(`Deleted iteration '${itId}'`);
      setSelectedIt(null);
      await loadAll();
    } catch (err) {
      toast.error('Failed to delete iteration: ' + err.message);
    }
  };

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="side-panel" style={{ maxWidth: 840 }} onClick={e => e.stopPropagation()}>
        <div className="side-panel-header">
          <span className="side-panel-title">⏱ Iteration, Sprint & Waterfall Gate Manager</span>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>

        <div className="panel-body" style={{ padding: 16, display: 'grid', gridTemplateColumns: '260px 1fr', gap: 16 }}>
          {/* Left list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, borderRight: '1px solid var(--border-color)', paddingRight: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 12, fontWeight: 600 }}>Iterations & Gates</span>
              <button className="btn btn-primary" style={{ fontSize: 11, padding: '2px 8px' }} onClick={() => {
                setSelectedIt(null);
                setId(`sprint-${Date.now().toString().slice(-4)}`);
                setTitle('New Sprint');
                setMethodology('scrum');
                setStatus('planned');
              }}>+ New</button>
            </div>

            {loading ? (
              <div className="panel-loading"><div className="spinner" /></div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, overflowY: 'auto' }}>
                {iterations.map(it => (
                  <div
                    key={it.id}
                    onClick={() => handleSelect(it)}
                    style={{
                      padding: 8,
                      borderRadius: 6,
                      background: selectedIt?.id === it.id ? 'var(--bg-tertiary, #21262d)' : 'var(--bg-secondary)',
                      border: '1px solid var(--border-color)',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ fontWeight: 600, fontSize: 12, color: 'var(--text-primary)' }}>{it.title || it.id}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                      <span className="mono" style={{ color: 'var(--accent-color, #4ea8de)' }}>{(it.methodology || 'scrum').toUpperCase()}</span> | {it.status}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right form & metrics */}
          <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600 }}>Iteration ID</label>
                <input type="text" value={id} onChange={e => setId(e.target.value)} required style={{ width: '100%', fontSize: 12, padding: 6 }} />
              </div>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600 }}>Methodology Mode</label>
                <select value={methodology} onChange={e => setMethodology(e.target.value)} style={{ width: '100%', fontSize: 12, padding: 6 }}>
                  <option value="scrum">Scrum (Sprint Backlog & Velocity)</option>
                  <option value="waterfall">Waterfall (Phase & Gate Review)</option>
                  <option value="wagile">Wagile (Hybrid Sprint + Gate)</option>
                  <option value="kanban">Kanban (Continuous Flow)</option>
                </select>
              </div>
            </div>

            <div>
              <label style={{ fontSize: 11, fontWeight: 600 }}>Title / Milestone Name</label>
              <input type="text" value={title} onChange={e => setTitle(e.target.value)} required style={{ width: '100%', fontSize: 12, padding: 6 }} />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600 }}>Start Date</label>
                <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} style={{ width: '100%', fontSize: 12, padding: 6 }} />
              </div>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600 }}>End Date</label>
                <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} style={{ width: '100%', fontSize: 12, padding: 6 }} />
              </div>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600 }}>Gate / Milestone Date</label>
                <input type="date" value={milestoneDate} onChange={e => setMilestoneDate(e.target.value)} style={{ width: '100%', fontSize: 12, padding: 6 }} />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600 }}>Story Point Capacity</label>
                <input type="number" value={capacity} onChange={e => setCapacity(e.target.value)} style={{ width: '100%', fontSize: 12, padding: 6 }} />
              </div>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600 }}>Status</label>
                <select value={status} onChange={e => setStatus(e.target.value)} style={{ width: '100%', fontSize: 12, padding: 6 }}>
                  <option value="planned">Planned</option>
                  <option value="active">Active</option>
                  <option value="completed">Completed</option>
                  <option value="closed">Closed</option>
                </select>
              </div>
            </div>

            {/* Metrics summary card */}
            {metrics && (
              <div style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: 6,
                padding: 12,
                fontSize: 11,
              }}>
                <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>
                  Progress & Burndown Metrics ({metrics.completion_percentage}% Approved)
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 8 }}>
                  <div>Total Items: <b>{metrics.total_requirements}</b></div>
                  <div>Approved: <b style={{ color: 'var(--success-color, #4ea8de)' }}>{metrics.approved}</b></div>
                  <div>In Review: <b>{metrics.in_review}</b></div>
                  <div>Draft: <b>{metrics.draft}</b></div>
                </div>
              </div>
            )}

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
              {selectedIt && (
                <button type="button" className="btn btn-danger" style={{ fontSize: 11 }} onClick={() => handleDelete(selectedIt.id)}>
                  Delete
                </button>
              )}
              <button type="submit" className="btn btn-primary" style={{ fontSize: 11 }}>
                Save Iteration
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
