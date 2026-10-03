vi.mock('@uiw/react-codemirror', () => ({ default: () => null }));

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useEffect } from 'react';
import { AppProvider, useApp } from '../AppContext';
import { WorkflowStateWidget } from '../components/Editor.jsx';
import { resolveWorkflow } from '../workflow';

const st = (id, label) => ({ id, label, colour: '#888' });
const hierarchy = {
  types: { initiative: { workflow: 'lightweight' }, story: { workflow: 'sprint' } },
  workflows: {
    lightweight: { states: [st('draft', 'Draft'), st('active', 'Active')], transitions: { draft: ['active'] } },
    sprint: { states: [st('backlog', 'Backlog'), st('ready', 'Ready')], transitions: { backlog: ['ready'] } },
  },
};
const fallback = { states: [st('draft', 'Draft'), st('approved', 'Approved')], transitions: { draft: ['approved'] } };

describe('resolveWorkflow (MOD-04)', () => {
  it('uses the per-type workflow', () => {
    expect(resolveWorkflow('initiative', hierarchy, fallback).states.map(s => s.id)).toEqual(['draft', 'active']);
    expect(resolveWorkflow('story', hierarchy, fallback).states.map(s => s.id)).toEqual(['backlog', 'ready']);
  });
  it('falls back to the global workflow for unknown types or no hierarchy', () => {
    expect(resolveWorkflow('functional', hierarchy, fallback)).toEqual(fallback);
    expect(resolveWorkflow('initiative', null, fallback)).toEqual(fallback);
  });
  it('returns null when nothing is configured', () => {
    expect(resolveWorkflow('x', null, null)).toBeNull();
  });
});

function Seed({ children }) {
  const { dispatch } = useApp();
  useEffect(() => { dispatch({ type: 'SET_HIERARCHY', payload: hierarchy }); }, [dispatch]);
  return children;
}

describe('WorkflowStateWidget (MOD-04)', () => {
  it('offers draft -> active for an Initiative and reports the transition', async () => {
    const onTransition = vi.fn();
    render(
      <AppProvider><Seed>
        <WorkflowStateWidget uid="u" status="draft" reqType="initiative" onTransition={onTransition} />
      </Seed></AppProvider>
    );
    const btn = await screen.findByText('Active');
    fireEvent.click(btn);
    expect(onTransition).toHaveBeenCalledWith('active');
  });
});
