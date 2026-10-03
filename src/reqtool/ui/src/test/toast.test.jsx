import { describe, it, expect } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { AppProvider, useApp } from '../AppContext';

function Probe() {
  const { toast, state } = useApp();
  return (
    <div>
      <button onClick={() => toast.success('ok-msg')}>s</button>
      <button onClick={() => toast.error('err-msg')}>e</button>
      <button onClick={() => toast.info('info-msg')}>i</button>
      <button onClick={() => toast('plain-msg', 'warn')}>p</button>
      <ul>{state.toasts.map(t => <li key={t.id}>{t.kind}:{t.message}</li>)}</ul>
    </div>
  );
}

describe('toast helpers', () => {
  it('supports toast(), toast.success/error/info', () => {
    render(<AppProvider><Probe /></AppProvider>);
    for (const n of ['s', 'e', 'i', 'p']) {
      act(() => screen.getByText(n).click());
    }
    expect(screen.getByText('success:ok-msg')).toBeTruthy();
    expect(screen.getByText('error:err-msg')).toBeTruthy();
    expect(screen.getByText('info:info-msg')).toBeTruthy();
    expect(screen.getByText('warn:plain-msg')).toBeTruthy();
  });
});
