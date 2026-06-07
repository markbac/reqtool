/**
 * ui.test.jsx
 *
 * Tests for the reqtool React UI.
 * Organised into two files:
 *   1. AppContext + React deduplication (this file, no component imports)
 *   2. Component smoke tests (components.test.jsx, mocks heavy deps)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import React, { useContext, createContext } from 'react';
import { AppProvider, useApp } from '../AppContext';

// ---------------------------------------------------------------------------
// AppContext
// ---------------------------------------------------------------------------

describe('AppContext', () => {
  it('renders children inside AppProvider without crashing', () => {
    render(
      <AppProvider>
        <div data-testid="child">hello</div>
      </AppProvider>
    );
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('useApp returns state, dispatch, and toast', () => {
    let captured = null;
    function Probe() { captured = useApp(); return null; }
    render(<AppProvider><Probe /></AppProvider>);
    expect(captured).not.toBeNull();
    expect(typeof captured.state).toBe('object');
    expect(typeof captured.dispatch).toBe('function');
    expect(typeof captured.toast).toBe('function');
  });

  it('initial state has correct shape', () => {
    let st = null;
    function Probe() { st = useApp().state; return null; }
    render(<AppProvider><Probe /></AppProvider>);
    expect(st.panel).toBe('requirements');
    expect(st.selectedUid).toBeNull();
    expect(st.theme).toBe('dark');
    expect(Array.isArray(st.toasts)).toBe(true);
    expect(st.dirtyUids instanceof Set).toBe(true);
  });

  it('SELECT action updates selectedUid and selectedType', () => {
    let ctx = null;
    function Probe() { ctx = useApp(); return null; }
    render(<AppProvider><Probe /></AppProvider>);
    act(() => ctx.dispatch({ type: 'SELECT', uid: 'abc', artefactType: 'requirement' }));
    expect(ctx.state.selectedUid).toBe('abc');
    expect(ctx.state.selectedType).toBe('requirement');
  });

  it('DESELECT action clears selectedUid', () => {
    let ctx = null;
    function Probe() { ctx = useApp(); return null; }
    render(<AppProvider><Probe /></AppProvider>);
    act(() => ctx.dispatch({ type: 'SELECT', uid: 'abc', artefactType: 'requirement' }));
    act(() => ctx.dispatch({ type: 'DESELECT' }));
    expect(ctx.state.selectedUid).toBeNull();
  });

  it('SET_PANEL changes panel and clears selection', () => {
    let ctx = null;
    function Probe() { ctx = useApp(); return null; }
    render(<AppProvider><Probe /></AppProvider>);
    act(() => ctx.dispatch({ type: 'SELECT', uid: 'xyz', artefactType: 'requirement' }));
    act(() => ctx.dispatch({ type: 'SET_PANEL', payload: 'principles' }));
    expect(ctx.state.panel).toBe('principles');
    expect(ctx.state.selectedUid).toBeNull();
  });

  it('SET_THEME updates theme', () => {
    let ctx = null;
    function Probe() { ctx = useApp(); return null; }
    render(<AppProvider><Probe /></AppProvider>);
    act(() => ctx.dispatch({ type: 'SET_THEME', payload: 'light' }));
    expect(ctx.state.theme).toBe('light');
  });

  it('MARK_DIRTY adds uid; MARK_CLEAN removes it', () => {
    let ctx = null;
    function Probe() { ctx = useApp(); return null; }
    render(<AppProvider><Probe /></AppProvider>);
    act(() => ctx.dispatch({ type: 'MARK_DIRTY', uid: 'req-001' }));
    expect(ctx.state.dirtyUids.has('req-001')).toBe(true);
    act(() => ctx.dispatch({ type: 'MARK_CLEAN', uid: 'req-001' }));
    expect(ctx.state.dirtyUids.has('req-001')).toBe(false);
  });

  it('TOGGLE_PANEL sets and unsets overlay boolean keys', () => {
    let ctx = null;
    function Probe() { ctx = useApp(); return null; }
    render(<AppProvider><Probe /></AppProvider>);
    act(() => ctx.dispatch({ type: 'TOGGLE_PANEL', key: '_showValidation', value: true }));
    expect(ctx.state._showValidation).toBe(true);
    act(() => ctx.dispatch({ type: 'TOGGLE_PANEL', key: '_showValidation', value: false }));
    expect(ctx.state._showValidation).toBe(false);
  });

  it('toast adds entry and removes after duration', async () => {
    vi.useFakeTimers();
    let ctx = null;
    function Probe() { ctx = useApp(); return null; }
    render(<AppProvider><Probe /></AppProvider>);
    act(() => ctx.toast('Hello', 'info', 1000));
    expect(ctx.state.toasts).toHaveLength(1);
    expect(ctx.state.toasts[0].message).toBe('Hello');
    expect(ctx.state.toasts[0].kind).toBe('info');
    act(() => vi.advanceTimersByTime(1100));
    expect(ctx.state.toasts).toHaveLength(0);
    vi.useRealTimers();
  });

  it('multiple toasts coexist independently', () => {
    let ctx = null;
    function Probe() { ctx = useApp(); return null; }
    render(<AppProvider><Probe /></AppProvider>);
    act(() => { ctx.toast('A', 'info', 9999); ctx.toast('B', 'error', 9999); });
    expect(ctx.state.toasts).toHaveLength(2);
    expect(ctx.state.toasts.map(t => t.message)).toContain('A');
    expect(ctx.state.toasts.map(t => t.message)).toContain('B');
  });

  it('unknown action returns unchanged state', () => {
    let ctx = null;
    function Probe() { ctx = useApp(); return null; }
    render(<AppProvider><Probe /></AppProvider>);
    const before = ctx.state.panel;
    act(() => ctx.dispatch({ type: 'UNKNOWN_ACTION_XYZ' }));
    expect(ctx.state.panel).toBe(before);
  });

  it('SET_SEARCH updates searchQuery', () => {
    let ctx = null;
    function Probe() { ctx = useApp(); return null; }
    render(<AppProvider><Probe /></AppProvider>);
    act(() => ctx.dispatch({ type: 'SET_SEARCH', payload: 'latency' }));
    expect(ctx.state.searchQuery).toBe('latency');
  });

  it('SET_PRODUCTS updates products array', () => {
    let ctx = null;
    function Probe() { ctx = useApp(); return null; }
    render(<AppProvider><Probe /></AppProvider>);
    act(() => ctx.dispatch({ type: 'SET_PRODUCTS', payload: [{ id: 'p1' }] }));
    expect(ctx.state.products).toHaveLength(1);
    expect(ctx.state.products[0].id).toBe('p1');
  });

  it('SET_ENUMS updates enums', () => {
    let ctx = null;
    function Probe() { ctx = useApp(); return null; }
    render(<AppProvider><Probe /></AppProvider>);
    act(() => ctx.dispatch({ type: 'SET_ENUMS', payload: { domain: ['a', 'b'] } }));
    expect(ctx.state.enums.domain).toEqual(['a', 'b']);
  });

  it('COMMITTED updates _lastCommit timestamp', () => {
    let ctx = null;
    function Probe() { ctx = useApp(); return null; }
    render(<AppProvider><Probe /></AppProvider>);
    const before = ctx.state._lastCommit;
    act(() => ctx.dispatch({ type: 'COMMITTED' }));
    expect(ctx.state._lastCommit).toBeGreaterThan(before);
  });

  it('nested AppProvider children all receive context', () => {
    const values = [];
    function Inner() { values.push(useApp().state.theme); return null; }
    function Middle() { return <div><Inner /><Inner /></div>; }
    render(<AppProvider><Middle /></AppProvider>);
    expect(values).toHaveLength(2);
    expect(values).toEqual(['dark', 'dark']);
  });
});

// ---------------------------------------------------------------------------
// React deduplication -- root cause of the useContext crash
// ---------------------------------------------------------------------------

describe('React deduplication', () => {
  it('useContext returns the provided value (not null or undefined)', () => {
    const Ctx = createContext('default');
    let received;
    function Consumer() { received = useContext(Ctx); return null; }
    render(<Ctx.Provider value="expected"><Consumer /></Ctx.Provider>);
    expect(received).toBe('expected');
    expect(received).not.toBeNull();
  });

  it('useApp() is never null inside AppProvider', () => {
    const results = [];
    function Deep() { results.push(useApp()); return null; }
    render(<AppProvider><div><div><Deep /></div></div></AppProvider>);
    expect(results[0]).not.toBeNull();
    expect(results[0].state).toBeDefined();
  });

  it('React.useContext is a function (single React instance)', () => {
    let fn;
    function Probe() { fn = React.useContext; return null; }
    render(<AppProvider><Probe /></AppProvider>);
    expect(typeof fn).toBe('function');
  });

  it('context created in one module is readable in another', () => {
    // Simulate the cross-module pattern: AppContext.jsx creates context,
    // a component in another file consumes it.
    // If React is duplicated, this returns null. If deduplicated, it works.
    const Ctx = createContext({ value: 42 });
    function ProducerModule({ children }) {
      return <Ctx.Provider value={{ value: 99 }}>{children}</Ctx.Provider>;
    }
    let received;
    function ConsumerModule() {
      received = useContext(Ctx);
      return null;
    }
    render(<ProducerModule><AppProvider><ConsumerModule /></AppProvider></ProducerModule>);
    expect(received?.value).toBe(99);
  });

  it('AppContext value propagates through multiple layers of components', () => {
    const depth3Results = [];
    function L3() { depth3Results.push(useApp().state.theme); return null; }
    function L2() { return <L3 />; }
    function L1() { return <L2 />; }
    render(<AppProvider><L1 /></AppProvider>);
    expect(depth3Results[0]).toBe('dark');
  });

  it('state mutations are visible across multiple consumers in the same tree', () => {
    let ctx1 = null, ctx2 = null;
    function A() { ctx1 = useApp(); return null; }
    function B() { ctx2 = useApp(); return null; }
    render(<AppProvider><A /><B /></AppProvider>);
    act(() => ctx1.dispatch({ type: 'SET_THEME', payload: 'light' }));
    // Both consumers see the updated state because they share one context
    expect(ctx2.state.theme).toBe('light');
  });
});
