vi.mock('@uiw/react-codemirror', () => ({ default: () => null }));

const schema = {
  events: [{ id: 'requirement_created', label: 'Requirement created' }, { id: 'requirement_approved', label: 'Requirement approved' }],
  actions: [
    { id: 'set_field', label: 'Set field', requires: ['target_field', 'target_value'] },
    { id: 'add_tag', label: 'Add tag', requires: ['target_value'] },
  ],
};
let saved = [];
vi.mock('../api', () => ({
  api: {
    automation: {
      schema: vi.fn(async () => schema),
      getRules: vi.fn(async () => saved),
      updateRules: vi.fn(async (rules) => { saved = rules.map((r, i) => ({ id: `rule-${i}`, ...r })); return { saved: rules.length }; }),
    },
  },
}));

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AppProvider } from '../AppContext';
import { AutomationRulesPanel } from '../components/Advanced/AutomationRulesPanel.jsx';
import { api } from '../api';
import { ruleErrors } from '../automationRules';

describe('ruleErrors', () => {
  it('maps FastAPI 422 details to rule indexes', () => {
    const err = { detail: [
      { loc: ['body', 1, 'event'], msg: "Value error, unknown event 'x'" },
      { loc: ['body', 1], msg: 'Value error, action requires target_field' },
    ] };
    expect(ruleErrors(err)).toEqual({ 1: ["event: unknown event 'x'", 'action requires target_field'] });
  });
  it('ignores non-validation errors', () => {
    expect(ruleErrors(new Error('boom'))).toEqual({});
  });
});

describe('AutomationRulesPanel (UI-12)', () => {
  it('creates, saves and reloads a rule in the engine format', async () => {
    const { unmount } = render(<AppProvider><AutomationRulesPanel onClose={() => {}} /></AppProvider>);
    await screen.findByText('No automation rules configured yet.');
    fireEvent.click(screen.getByText('+ Add Automation Rule'));
    fireEvent.change(await screen.findByLabelText('Action'), { target: { value: 'add_tag' } });
    fireEvent.change(screen.getByLabelText('Target value'), { target: { value: 'ASIL-D' } });
    fireEvent.click(screen.getByText('Save Rules'));
    await waitFor(() => expect(api.automation.updateRules).toHaveBeenCalled());
    const sent = api.automation.updateRules.mock.calls[0][0];
    expect(Array.isArray(sent)).toBe(true);
    expect(sent[0]).toMatchObject({ event: 'requirement_created', action: 'add_tag', target_value: 'ASIL-D', condition: {} });
    expect(sent[0]).not.toHaveProperty('actions');
    expect(sent[0]).not.toHaveProperty('target_field');
    unmount();

    render(<AppProvider><AutomationRulesPanel onClose={() => {}} /></AppProvider>);
    expect(await screen.findAllByTestId('automation-rule')).toHaveLength(1);
    expect(screen.getByLabelText('Target value').value).toBe('ASIL-D');
  });

  it('shows server validation errors under the failing rule', async () => {
    saved = [{ id: 'rule-0', name: 'R', enabled: true, event: 'requirement_created', condition: {}, action: 'set_field' }];
    api.automation.updateRules.mockRejectedValueOnce(Object.assign(new Error('x'), {
      detail: [{ loc: ['body', 0], msg: 'Value error, action \'set_field\' requires target_field' }],
    }));
    render(<AppProvider><AutomationRulesPanel onClose={() => {}} /></AppProvider>);
    await screen.findAllByTestId('automation-rule');
    fireEvent.click(screen.getByText('Save Rules'));
    expect(await screen.findByRole('alert')).toHaveTextContent('requires target_field');
  });
});
