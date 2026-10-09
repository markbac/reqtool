vi.mock('@uiw/react-codemirror', () => ({ default: () => null }));
vi.mock('../components/MermaidView', () => ({ MermaidView: ({ source }) => <pre data-testid="diagram">{source}</pre> }));

const def = () => ({
  initial: 'draft',
  states: [
    { id: 'draft', label: 'Draft', colour: '#8b949e', terminal: false },
    { id: 'done', label: 'Done', colour: '#238636', terminal: true },
  ],
  transitions: { draft: ['done'], done: [] },
  guards: {
    draft: { requires_fields: [], requires_ac: false, requires_children_in: [], children_enforce: 'warn', message: '' },
    done: { requires_fields: [], requires_ac: false, requires_children_in: [], children_enforce: 'warn', message: '' },
  },
});

vi.mock('../api', () => ({
  api: {
    workflows: {
      list: vi.fn(async () => ({
        workflows: [{ id: 'simple', definition: def(), used_by: ['task'], errors: [], warnings: [], mermaid: 'flowchart LR' }],
        types: { task: 'simple', bug: 'simple' },
        known_fields: { title: 'Title', 'content.rationale': 'Rationale' },
      })),
      preview: vi.fn(async (d) => ({ errors: [], warnings: [], definition: d, mermaid: `flowchart LR\n  states ${d.states.length}` })),
      save: vi.fn(async () => ({})),
      create: vi.fn(async () => ({})),
      remove: vi.fn(async () => ({})),
      assign: vi.fn(async () => ({})),
    },
    workflow: { mermaid: vi.fn(async () => ({ mermaid: 'flowchart LR\n  fallback' })) },
    hierarchy: { get: vi.fn(async () => ({ types: {}, workflows: {} })) },
  },
}));

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useEffect } from 'react';
import { AppProvider, useApp } from '../AppContext';
import { WorkflowEditor, edit } from '../components/WorkflowEditor.jsx';
import { api } from '../api';

function As({ permissions, children }) {
  const { dispatch } = useApp();
  useEffect(() => { dispatch({ type: 'SET_PERMISSIONS', payload: { permissions, role: 'x' } }); }, [dispatch]);
  return children;
}
const ADMIN = ['read', 'write', 'delete', 'manage_workflow'];

describe('workflow edits (pure)', () => {
  it('adds a state with explicit guard and no moves', () => {
    const next = edit.addState(def(), 'review');
    expect(next.states.map(s => s.id)).toEqual(['draft', 'done', 'review']);
    expect(next.transitions.review).toEqual([]);
    expect(next.guards.review.children_enforce).toBe('warn');
  });
  it('removing a state clears every reference to it', () => {
    let d = edit.setGuard(def(), 'draft', { requires_children_in: ['done'] });
    d = edit.removeState(d, 'done');
    expect(d.states.map(s => s.id)).toEqual(['draft']);
    expect(d.transitions).toEqual({ draft: [] });
    expect(d.guards.draft.requires_children_in).toEqual([]);
  });
  it('removing the start state picks another', () => {
    expect(edit.removeState(def(), 'draft').initial).toBe('done');
  });
  it('toggles a move on and off', () => {
    const on = edit.toggleTransition(def(), 'done', 'draft');
    expect(on.transitions.done).toEqual(['draft']);
    expect(edit.toggleTransition(on, 'done', 'draft').transitions.done).toEqual([]);
  });
  it('does not change its input', () => {
    const d = def(); edit.addState(d, 'x'); edit.toggleTransition(d, 'done', 'draft');
    expect(d).toEqual(def());
  });
});

describe('WorkflowEditor', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lets an administrator add a state, shows the server diagram and saves', async () => {
    render(<AppProvider><As permissions={ADMIN}><WorkflowEditor onClose={() => {}} /></As></AppProvider>);
    await screen.findByLabelText('New state id');
    fireEvent.change(screen.getByLabelText('New state id'), { target: { value: 'review' } });
    fireEvent.click(screen.getByText('Add state'));
    await waitFor(() => expect(screen.getByTestId('diagram').textContent).toContain('states 3'));
    fireEvent.click(screen.getByLabelText('draft to review'));
    fireEvent.click(screen.getByText('Save'));
    await waitFor(() => expect(api.workflows.save).toHaveBeenCalled());
    const [id, saved] = api.workflows.save.mock.calls[0];
    expect(id).toBe('simple');
    expect(saved.states.map(s => s.id)).toContain('review');
    expect(saved.transitions.draft).toEqual(['done', 'review']);
  });

  it('rejects a bad state id', async () => {
    render(<AppProvider><As permissions={ADMIN}><WorkflowEditor onClose={() => {}} /></As></AppProvider>);
    await screen.findByLabelText('New state id');
    fireEvent.change(screen.getByLabelText('New state id'), { target: { value: 'Bad Id' } });
    expect(screen.getByText('Add state')).toBeDisabled();
  });

  it('blocks saving while the server reports errors', async () => {
    api.workflows.preview.mockResolvedValue({ errors: ['State done cannot be reached'], warnings: [], mermaid: 'x' });
    render(<AppProvider><As permissions={ADMIN}><WorkflowEditor onClose={() => {}} /></As></AppProvider>);
    await screen.findByText('State done cannot be reached');
    fireEvent.click(screen.getByLabelText('done to draft'));
    expect(screen.getByText('Save')).toBeDisabled();
  });

  it('sets what a move into a state needs', async () => {
    render(<AppProvider><As permissions={ADMIN}><WorkflowEditor onClose={() => {}} /></As></AppProvider>);
    await screen.findByLabelText('New state id');
    fireEvent.click(screen.getAllByRole('button', { name: /done/ }).find(b => b.getAttribute('aria-expanded') !== null));
    fireEvent.click(screen.getByLabelText('Rationale'));
    fireEvent.click(screen.getByText('Save'));
    await waitFor(() => expect(api.workflows.save).toHaveBeenCalled());
    expect(api.workflows.save.mock.calls[0][1].guards.done.requires_fields).toEqual(['content.rationale']);
  });

  it('assigns a workflow to an item type', async () => {
    render(<AppProvider><As permissions={ADMIN}><WorkflowEditor onClose={() => {}} /></As></AppProvider>);
    const select = await screen.findByLabelText('Workflow for bug');
    fireEvent.change(select, { target: { value: 'simple' } });
    await waitFor(() => expect(api.workflows.assign).toHaveBeenCalledWith('bug', 'simple'));
  });

  it('is read only for anyone else', async () => {
    render(<AppProvider><As permissions={['read', 'write']}><WorkflowEditor onClose={() => {}} /></As></AppProvider>);
    await screen.findByText(/only an administrator can change them/);
    expect(screen.queryByLabelText('New state id')).toBeNull();
    expect(screen.queryByText('Save')).toBeNull();
    expect(screen.queryByText('Delete')).toBeNull();
    expect(screen.getByLabelText('draft to done')).toBeDisabled();
  });

  it('shows the fallback workflow on request', async () => {
    render(<AppProvider><As permissions={ADMIN}><WorkflowEditor onClose={() => {}} /></As></AppProvider>);
    fireEvent.click(await screen.findByText('Show its diagram'));
    await waitFor(() => expect(screen.getAllByTestId('diagram').some(d => d.textContent.includes('fallback'))).toBe(true));
  });
});
