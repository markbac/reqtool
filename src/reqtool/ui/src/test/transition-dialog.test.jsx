vi.mock('@uiw/react-codemirror', () => ({ default: () => null }));

vi.mock('../api', () => ({ api: { requirements: { transitions: vi.fn() } } }));

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useEffect } from 'react';
import { AppProvider, useApp } from '../AppContext';
import { TransitionDialog, getPath, setPath, isFilled } from '../components/TransitionDialog.jsx';
import { WorkflowStateWidget, needsInput } from '../components/Editor.jsx';
import { api } from '../api';

const option = (over = {}) => ({
  to: 'approved', label: 'Approved', colour: '#238636', terminal: false, problem: null,
  requires: {
    fields: [{ path: 'content.rationale', label: 'Rationale', filled: false }, { path: 'safety_classification', label: 'Safety classification', filled: false }],
    acceptance_criteria: true, has_acceptance_criteria: false, children_in: [], children_enforce: 'off', open_children: [],
    message: 'Safety requirements need rationale first.',
  },
  ...over,
});
const draft = { uid: 'u', title: 'Brake', content: { description: 'Stop', rationale: '' }, acceptance_criteria: [] };

describe('field paths', () => {
  it('reads and writes dotted paths without changing the original', () => {
    expect(getPath(draft, 'content.description')).toBe('Stop');
    expect(getPath(draft, 'nope.deep')).toBeUndefined();
    const next = setPath(draft, 'content.rationale', 'Why');
    expect(next.content).toEqual({ description: 'Stop', rationale: 'Why' });
    expect(draft.content.rationale).toBe('');
  });
  it('knows what counts as filled', () => {
    expect([isFilled(''), isFilled('  '), isFilled([]), isFilled(null), isFilled('x'), isFilled(['a'])]).toEqual([false, false, false, false, true, true]);
  });
});

describe('needsInput', () => {
  it('is false when nothing is required or everything is there', () => {
    expect(needsInput({ requires: { fields: [] } }, draft)).toBe(false);
    expect(needsInput(option(), { ...draft, safety_classification: 'B', content: { rationale: 'x' }, acceptance_criteria: [{ id: 'AC-1', text: 'a' }] })).toBe(false);
  });
  it('is true for a missing field, missing criteria, a problem or open children', () => {
    expect(needsInput(option(), draft)).toBe(true);
    expect(needsInput({ requires: { fields: [], acceptance_criteria: true } }, draft)).toBe(true);
    expect(needsInput({ problem: 'nope', requires: { fields: [] } }, draft)).toBe(true);
    expect(needsInput({ requires: { fields: [], children_enforce: 'warn', open_children: ['a'] } }, draft)).toBe(true);
  });
});

describe('TransitionDialog', () => {
  const setup = (props = {}) => {
    const onApply = vi.fn(); const onCancel = vi.fn();
    render(<AppProvider><TransitionDialog option={option()} draft={draft} onApply={onApply} onCancel={onCancel} {...props} /></AppProvider>);
    return { onApply, onCancel };
  };

  it('highlights what is needed and holds back the buttons until it is given', () => {
    setup();
    expect(screen.getByText('Safety requirements need rationale first.')).toBeInTheDocument();
    expect(screen.getAllByText('required').length).toBe(3);
    expect(screen.getByText('Apply to draft')).toBeDisabled();
    expect(screen.getByText(/Still needed: Rationale, Safety classification, acceptance criteria/)).toBeInTheDocument();
  });

  it('applies the typed values and can save at once', () => {
    const { onApply } = setup();
    fireEvent.change(screen.getByLabelText('Rationale'), { target: { value: 'Because' } });
    fireEvent.change(screen.getByLabelText('Safety classification'), { target: { value: 'ASIL-B' } });
    fireEvent.change(screen.getByLabelText('New acceptance criterion'), { target: { value: 'Stops in 40 m' } });
    fireEvent.click(screen.getByText('Add'));
    expect(screen.getByText('Apply and save')).toBeEnabled();
    fireEvent.click(screen.getByText('Apply and save'));
    const [next, save] = onApply.mock.calls[0];
    expect(save).toBe(true);
    expect(next.content.rationale).toBe('Because');
    expect(next.safety_classification).toBe('ASIL-B');
    expect(next.acceptance_criteria[0].text).toBe('Stops in 40 m');
  });

  it('shows every other field on request so any can be changed', () => {
    const { onApply } = setup({ option: option({ requires: { fields: [], acceptance_criteria: false, children_enforce: 'off', open_children: [], message: '' } }) });
    expect(screen.queryByLabelText('Owner')).toBeNull();
    fireEvent.click(screen.getByText(/Change other fields/));
    for (const label of ['Title', 'Description', 'Rationale', 'Owner', 'Assignee', 'Component', 'Estimate', 'Tags (comma separated)']) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
    fireEvent.change(screen.getByLabelText('Owner'), { target: { value: 'sam' } });
    fireEvent.change(screen.getByLabelText('Tags (comma separated)'), { target: { value: 'a, b' } });
    fireEvent.click(screen.getByText('Apply to draft'));
    const [next, save] = onApply.mock.calls[0];
    expect(save).toBe(false);
    expect(next.owner).toBe('sam');
    expect(next.tags).toEqual(['a', 'b']);
  });

  it('blocks the move when children must be finished first', () => {
    setup({ option: option({ requires: { fields: [], children_in: ['done'], children_enforce: 'error', open_children: [{ id: 'FR-002' }], message: '' } }) });
    expect(screen.getByRole('alert')).toHaveTextContent('FR-002');
    expect(screen.getByText('Apply to draft')).toBeDisabled();
  });

  it('cancels', () => {
    const { onCancel } = setup();
    fireEvent.click(screen.getByLabelText('Close'));
    expect(onCancel).toHaveBeenCalled();
  });
});

describe('WorkflowStateWidget with the pop-up', () => {
  const hierarchy = {
    types: { safety: { workflow: 'w' } },
    workflows: { w: { states: [{ id: 'reviewed', label: 'Reviewed', colour: '#111' }, { id: 'approved', label: 'Approved', colour: '#222' }, { id: 'draft', label: 'Draft', colour: '#333' }],
      transitions: { reviewed: ['approved', 'draft'] } } },
  };
  function Seed({ children }) {
    const { dispatch } = useApp();
    useEffect(() => { dispatch({ type: 'SET_HIERARCHY', payload: hierarchy }); }, [dispatch]);
    return children;
  }
  beforeEach(() => vi.clearAllMocks());

  it('moves straight away when nothing is required', async () => {
    api.requirements.transitions.mockResolvedValue({ transitions: [option({ to: 'draft', requires: { fields: [] } })] });
    const onTransition = vi.fn();
    render(<AppProvider><Seed><WorkflowStateWidget uid="u" status="reviewed" reqType="safety" draft={draft} onTransition={onTransition} /></Seed></AppProvider>);
    fireEvent.click(await screen.findByText('Draft'));
    await waitFor(() => expect(onTransition).toHaveBeenCalledWith('draft'));
  });

  it('asks for the missing data first, then reports the new draft', async () => {
    api.requirements.transitions.mockResolvedValue({ transitions: [option()] });
    const onTransition = vi.fn();
    render(<AppProvider><Seed><WorkflowStateWidget uid="u" status="reviewed" reqType="safety" draft={draft} onTransition={onTransition} /></Seed></AppProvider>);
    fireEvent.click(await screen.findByText('Approved'));
    await screen.findByRole('dialog');
    expect(onTransition).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Rationale'), { target: { value: 'Because' } });
    fireEvent.change(screen.getByLabelText('Safety classification'), { target: { value: 'B' } });
    fireEvent.change(screen.getByLabelText('New acceptance criterion'), { target: { value: 'AC text' } });
    fireEvent.click(screen.getByText('Add'));
    fireEvent.click(screen.getByText('Apply to draft'));
    expect(onTransition).toHaveBeenCalledTimes(1);
    const [to, next, save] = onTransition.mock.calls[0];
    expect([to, save, next.content.rationale]).toEqual(['approved', false, 'Because']);
  });

  it('hides the move buttons from a read-only role', async () => {
    function Viewer({ children }) {
      const { dispatch } = useApp();
      useEffect(() => { dispatch({ type: 'SET_PERMISSIONS', payload: { permissions: ['read'], role: 'viewer' } }); }, [dispatch]);
      return children;
    }
    render(<AppProvider><Seed><Viewer><WorkflowStateWidget uid="u" status="reviewed" reqType="safety" draft={draft} onTransition={() => {}} /></Viewer></Seed></AppProvider>);
    await screen.findByText('Reviewed');
    await waitFor(() => expect(screen.queryByText('Approved')).toBeNull());
  });
});
