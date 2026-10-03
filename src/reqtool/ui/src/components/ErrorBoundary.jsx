import { Component } from 'react';

/**
 * Catches render errors below it so one bad record cannot blank the whole app.
 * `onReset` runs before the children are rendered again (for example to close the panel that crashed).
 */
export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) { return { error }; }

  componentDidCatch(error, info) {
    console.error('Render error caught by ErrorBoundary:', error, info?.componentStack);
  }

  reset = () => {
    try { this.props.onReset?.(); } finally { this.setState({ error: null }); }
  };

  render() {
    if (!this.state.error) return this.props.children;
    const compact = this.props.scope === 'panel';
    return (
      <div role="alert" className="error-boundary"
        style={{ padding: 16, margin: compact ? 0 : 24, background: 'var(--bg-secondary, #161b22)',
                 border: '1px solid var(--border, #30363d)', borderRadius: 6, position: compact ? 'fixed' : 'static',
                 top: compact ? 60 : undefined, right: compact ? 16 : undefined, zIndex: 1000, maxWidth: 420 }}>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>
          {compact ? 'This panel hit an error and was closed.' : 'Something went wrong.'}
        </div>
        <div className="mono" style={{ fontSize: 11, color: 'var(--text-muted, #8b949e)', marginBottom: 10, wordBreak: 'break-word' }}>
          {String(this.state.error?.message || this.state.error)}
        </div>
        <button className="btn btn-primary" onClick={this.reset}>{compact ? 'Dismiss' : 'Try again'}</button>
        {!compact && <button className="btn btn-ghost" style={{ marginLeft: 8 }} onClick={() => window.location.reload()}>Reload</button>}
      </div>
    );
  }
}
