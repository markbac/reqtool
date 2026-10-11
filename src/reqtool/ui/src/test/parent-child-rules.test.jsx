vi.mock('@uiw/react-codemirror', () => ({ default: () => null }));

vi.mock('../api', () => ({
  api: {
    requirements: { transitions: vi.fn() },
    rules: {
      get: vi.fn(), save: vi.fn(async () => ({})), preview: vi.fn(), overrides: vi.fn(),
    },
  },
}));

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useEffect } from 'react';
import { AppProvider, useApp } from '../AppContext';
import { TransitionDialog } from '../components/TransitionDialog.jsx';
import { needsInput } from '../components/Editor.jsx';
import { ForceDialog, SuggestDialog, ruleBlock, rollupSummary } from '../components/RuleDialogs.jsx';
import { RulesPanel, rulesEdit } from '../components/RulesPanel.jsx';
import { api } from '../api';

function As({ permissions, children }) {
  const { dispatch } = useApp();
  useEffect(() => { dispatch({ type: 'SET_PERMISSIONS', payload: { permissions, role: 'x' } }); }, [dispatch]);
  return children;
}

const blockingCheck = { rule: 'no-start-under-closed', label: 'No work under a closed parent', mode: 'error',
  message: 'epic EP-1, two levels up, is cancelled' };

describe('helpers', () => {
  it('recognises a rule block and nothing else', () => {
    const err = { status: 409, detail: { error: 'workflow_guard', rules: [blockingCheck], can_force: true, message: 'm' } };
    expect(ruleBlock(err)).toEqual({ rules: [blockingCheck], canForce: true, message: 'm' });
    expect(ruleBlock({ status: 409, detail: { error: 'workflow_guard', message: 'plain guard' } })).toBeNull();
    expect(ruleBlock({ status: 500 })).toBeNull();
    expect(ruleBlock(null)).toBeNull();
  });
  it('summarises applied and blocked roll-ups', () => {
    expect(rollupSummary(undefined)).toBe('');
    const text = rollupSummary({ applied: [{ id: 'FEA-1', to: 'in_progress' }], blocked: [{ id: 'EP-1', reason: 'no move' }] });
    expect(text).toContain('FEA-1 to in_progress moved by rule');
    expect(text).toContain('could not move EP-1 (no move)');
  });
  it('a rule check makes the move ask first; suggestions are offered after the save instead', () => {
    expect(needsInput({ requires: { fields: [] }, rules: { checks: [blockingCheck] } }, {})).toBe(true);
    expect(needsInput({ requires: { fields: [] }, rules: { suggested: [{ uid: 'f' }] } }, {})).toBe(false);
    expect(needsInput({ requires: { fields: [] }, rules: { checks: [], suggested: [], auto: [{ uid: 'f' }] } }, {})).toBe(false);
  });
});

describe('ForceDialog', () => {
  it('will not force without a reason', () => {
    const onForce = vi.fn();
    render(<ForceDialog block={{ rules: [blockingCheck], canForce: true }} onForce={onForce} onCancel={() => {}} />);
    expect(screen.getByText(/two levels up/)).toBeInTheDocument();
    const go = screen.getByRole('button', { name: 'Force anyway' });
    expect(go).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/Reason for forcing it/), { target: { value: '  agreed with the PO  ' } });
    expect(go).not.toBeDisabled();
    fireEvent.click(go);
    expect(onForce).toHaveBeenCalledWith('agreed with the PO');
  });
  it('offers no way past a rule the role may not override', () => {
    render(<ForceDialog block={{ rules: [blockingCheck], canForce: false }} onForce={() => {}} onCancel={() => {}} />);
    expect(screen.queryByRole('button', { name: 'Force anyway' })).toBeNull();
    expect(screen.getByText(/may not go past this rule/)).toBeInTheDocument();
  });
});

describe('SuggestDialog', () => {
  it('moves only the ticked items', () => {
    const onAccept = vi.fn();
    const items = [{ uid: 'f', id: 'FEA-1', from: 'backlog', to: 'in_progress', label: 'Roll up: started', because: 'ST-1' },
      { uid: 'e', id: 'EP-1', from: 'backlog', to: 'in_progress', label: 'Roll up: started', because: 'FEA-1' }];
    render(<SuggestDialog suggestions={items} onAccept={onAccept} onDismiss={() => {}} />);
    fireEvent.click(screen.getAllByRole('checkbox')[1]);
    fireEvent.click(screen.getByRole('button', { name: 'Move selected' }));
    expect(onAccept).toHaveBeenCalledWith([items[0]]);
  });
});

describe('TransitionDialog with rules', () => {
  const option = (rules) => ({ to: 'in_progress', label: 'In progress', requires: { fields: [] }, rules });
  const draft = { uid: 'u', title: 'T', content: {} };
  const setup = (rules, permissions = ['read', 'write', 'override_rules']) => {
    const onApply = vi.fn();
    render(<AppProvider><As permissions={permissions}>
      <TransitionDialog option={option(rules)} draft={draft} onApply={onApply} onCancel={() => {}} />
    </As></AppProvider>);
    return onApply;
  };

  it('blocks on an error rule until it is forced with a reason, then passes the force on', async () => {
    const onApply = setup({ checks: [blockingCheck] });
    const save = screen.getByRole('button', { name: 'Apply and save' });
    expect(save).toBeDisabled();
    fireEvent.click(await screen.findByLabelText('Force anyway'));
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Reason for forcing'), { target: { value: 'customer escalation' } });
    expect(save).not.toBeDisabled();
    fireEvent.click(save);
    expect(onApply.mock.calls[0][2]).toMatchObject({ force: true, reason: 'customer escalation' });
  });

  it('hides the force option from a role that cannot override', () => {
    setup({ checks: [blockingCheck] }, ['read', 'write']);
    expect(screen.queryByLabelText('Force anyway')).toBeNull();
    expect(screen.getByRole('button', { name: 'Apply and save' })).toBeDisabled();
  });

  it('a warning does not block and suggestions are ticked by default and can be declined', () => {
    const onApply = setup({
      checks: [{ ...blockingCheck, mode: 'warn', message: 'FEA-1 has open children' }],
      suggested: [{ uid: 'f', id: 'FEA-1', to: 'in_progress', label: 'Roll up: started' }],
      auto: [{ id: 'EP-1', to: 'in_progress' }],
    });
    expect(screen.getByText(/FEA-1 has open children/)).toBeInTheDocument();
    expect(screen.getByText(/Also moves automatically: EP-1 to in_progress/)).toBeInTheDocument();
    const tick = screen.getByRole('checkbox');
    expect(tick).toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'Apply and save' }));
    expect(onApply.mock.calls[0][2].accept.map(s => s.uid)).toEqual(['f']);
    fireEvent.click(tick);
    fireEvent.click(screen.getByRole('button', { name: 'Apply and save' }));
    expect(onApply.mock.calls[1][2].accept).toEqual([]);
  });
});

describe('rules panel', () => {
  const info = () => ({
    override: 'editor', problems: [],
    modes: { checks: ['off', 'warn', 'error'], changes: ['off', 'suggest', 'auto'] },
    scopes: { up: ['parent', 'ancestors'], down: ['children', 'descendants'], complete: ['children', 'descendants'] },
    rules: [
      { id: 'up1', kind: 'up', label: 'No work under a closed parent', scope: 'ancestors', mode: 'warn', when_in: ['@terminal'], to: ['@started'], levels: null, override: null },
      { id: 'done1', kind: 'complete', label: 'Roll up: complete', scope: 'children', mode: 'suggest', when_in: [], to: [], levels: null, override: null },
    ],
  });
  beforeEach(() => {
    api.rules.get.mockResolvedValue(info());
    api.rules.overrides.mockResolvedValue({ overrides: [{ uid: 'a', id: 'US-1', status: 'in_progress', rules: ['up1'], by: 'ed', reason: 'Customer asked' }] });
    api.rules.save.mockClear();
  });

  it('pure edits do not change the original', () => {
    const cfg = { override: 'editor', rules: info().rules };
    const next = rulesEdit.setRule(cfg, 'up1', { mode: 'error' });
    expect(next.rules[0].mode).toBe('error');
    expect(cfg.rules[0].mode).toBe('warn');
    expect(rulesEdit.setOverride(cfg, 'admin').override).toBe('admin');
  });

  it('shows the matrix, saves a changed mode and lists forced moves', async () => {
    render(<AppProvider><As permissions={['read', 'write', 'manage_workflow']}><RulesPanel /></As></AppProvider>);
    const mode = await screen.findByLabelText('Mode for up1');
    expect(mode.value).toBe('warn');
    expect(screen.getByLabelText('Scope for done1').value).toBe('children');
    expect(await screen.findByText('Customer asked')).toBeInTheDocument();
    const save = screen.getByRole('button', { name: 'Save rules' });
    expect(save).toBeDisabled();
    fireEvent.change(mode, { target: { value: 'error' } });
    fireEvent.click(save);
    await waitFor(() => expect(api.rules.save).toHaveBeenCalled());
    expect(api.rules.save.mock.calls[0][0].rules[0].mode).toBe('error');
  });

  it('is read-only without manage_workflow', async () => {
    render(<AppProvider><As permissions={['read', 'write']}><RulesPanel /></As></AppProvider>);
    expect(await screen.findByLabelText('Mode for up1')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Save rules' })).toBeNull();
  });

  it('dry run lists what would happen', async () => {
    api.rules.preview.mockResolvedValue({
      checks: [{ rule: 'up1', mode: 'error', message: 'EP-1 is cancelled' }],
      auto: [{ uid: 'f', id: 'FEA-1', from: 'backlog', to: 'in_progress', label: 'Roll up: started' }],
      suggested: [], blocked: [{ uid: 'e', kind: 'start', id: 'EP-1', reason: 'owner required' }],
    });
    render(<AppProvider><As permissions={['read', 'write', 'manage_workflow']}><RulesPanel /></As></AppProvider>);
    fireEvent.change(await screen.findByLabelText('Sample item'), { target: { value: 'US-1' } });
    fireEvent.change(screen.getByLabelText('Move to state'), { target: { value: 'in_progress' } });
    fireEvent.click(screen.getByRole('button', { name: 'Dry run' }));
    const out = await screen.findByLabelText('Dry run result');
    expect(out).toHaveTextContent('Blocked: EP-1 is cancelled');
    expect(out).toHaveTextContent('Would move FEA-1 from backlog to in_progress');
    expect(out).toHaveTextContent('Could not move EP-1: owner required');
    expect(api.rules.preview).toHaveBeenCalledWith('US-1', 'in_progress');
  });
});

describe('raising work from a triaged issue', () => {
  it('offers a defect for a defect issue and a story for an enhancement, and nothing else', async () => {
    const { RaiseButton } = await import('../components/Editor.jsx');
    const show = (item) => render(<AppProvider><As permissions={['read', 'write']}><RaiseButton item={item} /></As></AppProvider>);
    const defect = show({ uid: 'i', id: 'ISS-1', req_type: 'issue', status: 'defect' });
    expect(screen.getByRole('button', { name: 'Raise a defect' })).toBeInTheDocument();
    defect.unmount();
    const story = show({ uid: 'i', id: 'ISS-1', req_type: 'issue', status: 'enhancement' });
    expect(screen.getByRole('button', { name: 'Raise a story' })).toBeInTheDocument();
    story.unmount();
    const other = show({ uid: 'i', id: 'ISS-1', req_type: 'issue', status: 'in_triage' });
    expect(screen.queryByRole('button')).toBeNull();
    other.unmount();
    show({ uid: 'b', id: 'BG-1', req_type: 'bug', status: 'defect' });
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('is hidden from viewers', async () => {
    const { RaiseButton } = await import('../components/Editor.jsx');
    render(<AppProvider><As permissions={['read']}><RaiseButton item={{ uid: 'i', id: 'ISS-1', req_type: 'issue', status: 'defect' }} /></As></AppProvider>);
    expect(screen.queryByRole('button')).toBeNull();
  });
});
