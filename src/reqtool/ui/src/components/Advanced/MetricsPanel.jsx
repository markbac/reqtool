import { useState, useEffect } from 'react';
import { api } from '../../api';
import { Panel } from './Panel';

export function MetricsPanel({ onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.metrics.get().then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, []);

  const pct = (n, total) => total ? Math.round(n / total * 100) : 0;

  const STATUS_COLOURS = {
    approved: 'var(--status-approved)', in_review: 'var(--accent-orange)',
    reviewed: 'var(--accent-blue)', draft: 'var(--text-muted)',
    deprecated: 'var(--accent-red)',
  };

  return (
    <Panel title="Metrics" onClose={onClose} width={540}>
      {loading && <div className="panel-loading"><div className="spinner" /></div>}
      {!loading && !data && <div className="text-muted">Could not load metrics.</div>}
      {data && (<>
        <div className="metrics-headlines">
          {[
            { label: 'Requirements', value: data.totals.requirements },
            { label: 'Principles',   value: data.totals.principles },
            { label: 'TBDs',         value: data.totals.tbds, warn: data.totals.open_tbds > 0 },
            { label: 'Open TBDs',    value: data.totals.open_tbds, warn: data.totals.open_tbds > 0 },
          ].map(({ label, value, warn }) => (
            <div key={label} className="metrics-headline-card">
              <div className={`metrics-headline-value ${warn ? 'metrics-warn' : ''}`}>{value}</div>
              <div className="metrics-headline-label">{label}</div>
            </div>
          ))}
        </div>

        <div className="metrics-section-title">Approval funnel</div>
        <div className="metrics-funnel">
          {Object.entries(data.status).sort((a,b) => b[1]-a[1]).map(([s, n]) => (
            <div key={s} className="metrics-bar-row">
              <span className="metrics-bar-label">{s}</span>
              <div className="metrics-bar-track">
                <div className="metrics-bar-fill"
                  style={{ width: pct(n, data.totals.requirements) + '%', background: STATUS_COLOURS[s] || 'var(--border)' }} />
              </div>
              <span className="metrics-bar-count">{n}</span>
            </div>
          ))}
        </div>
        <div className="metrics-approval-rate">
          Approval rate: <strong>{data.approval_funnel.approval_rate_pct}%</strong>
        </div>

        <div className="metrics-section-title">Quality gaps</div>
        {Object.entries(data.quality_gaps).map(([key, n]) => (
          <div key={key} className="metrics-bar-row">
            <span className="metrics-bar-label">{key.replace(/_/g,' ')}</span>
            <div className="metrics-bar-track">
              <div className="metrics-bar-fill"
                style={{ width: pct(n, data.totals.requirements) + '%', background: n > 0 ? 'var(--accent-orange)' : 'var(--border)' }} />
            </div>
            <span className="metrics-bar-count" style={{ color: n > 0 ? 'var(--accent-orange)' : 'var(--text-muted)' }}>{n}</span>
          </div>
        ))}

        <div className="metrics-section-title">Activity</div>
        <div className="metrics-velocity">
          <strong>{data.velocity.changes_last_30d}</strong> requirement changes in the last 30 days
        </div>

        <div className="metrics-section-title">By domain</div>
        <div className="metrics-domain-grid">
          {Object.entries(data.domain).sort((a,b) => b[1]-a[1]).map(([d, n]) => (
            <div key={d} className="metrics-domain-chip">
              <span>{d}</span><span className="metrics-domain-count">{n}</span>
            </div>
          ))}
        </div>
      </>)}
    </Panel>
  );
}
