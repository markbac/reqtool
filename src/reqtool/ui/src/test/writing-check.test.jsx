vi.mock('@uiw/react-codemirror', () => ({ default: () => null }));

const info = () => ({
  settings: {
    enabled: true, include_in_validation: false, fields: ['content.description'], statement_types: [], disabled_rules: ['REQ002'],
    severities: { DOC001: 'warning', DOC002: 'warning', DOC003: 'info', REQ001: 'warning', REQ002: 'info' },
    glossary: { API: ['api', 'Api'] }, redundant_phrases: { 'in order to': 'to' }, vague_terms: ['fast'], acronym_min_length: 3, allowed_acronyms: ['URL'],
    vale: { enabled: false, binary: 'vale', config_file: null, styles_path: null, styles: ['INCOSE'], disabled_checks: [], min_alert_level: 'warning', timeout_seconds: 10, include_in_validation: false },
  },
  file: '.reqtool/lint.yaml', exists: true, problems: [],
  rules: [{ id: 'DOC001', description: 'Glossary', enabled: true, severity: 'warning' }, { id: 'REQ002', description: 'Shall', enabled: false, severity: 'info' }],
  vale: { available: false, version: null }, defaults: {},
});
const report = {
  enabled: true, truncated: false,
  summary: { items: 2, issues: 1, items_with_issues: 1, by_severity: { error: 0, warning: 1, info: 0 }, by_rule: { DOC002: 1 } },
  issues: [{ uid: 'u1', id: 'FR-001', field: 'content.description', line: 3, rule: 'DOC002', category: 'Style', message: 'Redundant phrase', severity: 'warning', suggestion: 'to' }],
};
vi.mock('../api', () => ({
  api: {
    lint: { config: vi.fn(async () => info()), saveConfig: vi.fn(async (b) => ({ ...info(), settings: b })), all: vi.fn(async () => report) },
    requirements: { lint: vi.fn() },
  },
}));

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useEffect } from 'react';
import { AppProvider, useApp } from '../AppContext';
import { WritingCheckPanel, WritingStrip } from '../components/WritingCheck.jsx';
import { api } from '../api';

function As({ permissions, children }) {
  const { dispatch } = useApp();
  useEffect(() => { dispatch({ type: 'SET_PERMISSIONS', payload: { permissions, role: 'x' } }); }, [dispatch]);
  return children;
}

describe('WritingCheckPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lists the findings with where they are', async () => {
    render(<AppProvider><WritingCheckPanel onClose={() => {}} /></AppProvider>);
    expect(await screen.findByText('Redundant phrase')).toBeInTheDocument();
    expect(screen.getByText('FR-001')).toBeInTheDocument();
    expect(screen.getByText('content.description:3')).toBeInTheDocument();
    expect(screen.getByTestId('wc-summary')).toHaveTextContent('1 finding(s) in 1 of 2 item(s)');
  });

  it('lets an administrator change settings, writing back every setting', async () => {
    render(<AppProvider><As permissions={['read', 'manage_lint']}><WritingCheckPanel onClose={() => {}} /></As></AppProvider>);
    fireEvent.click(await screen.findByText('Settings'));
    fireEvent.click(await screen.findByLabelText('Enable REQ002'));
    fireEvent.change(screen.getByLabelText('Severity of DOC001'), { target: { value: 'error' } });
    fireEvent.click(screen.getByText('Save settings'));
    await waitFor(() => expect(api.lint.saveConfig).toHaveBeenCalled());
    const sent = api.lint.saveConfig.mock.calls[0][0];
    expect(sent.disabled_rules).toEqual([]);
    expect(sent.severities.DOC001).toBe('error');
    expect(sent.vale.binary).toBe('vale');
    expect(sent.glossary).toEqual({ API: ['api', 'Api'] });
  });

  it('parses the glossary and phrase boxes', async () => {
    render(<AppProvider><As permissions={['read', 'manage_lint']}><WritingCheckPanel onClose={() => {}} /></As></AppProvider>);
    fireEvent.click(await screen.findByText('Settings'));
    fireEvent.change(await screen.findByLabelText(/Glossary/), { target: { value: 'MQTT: mqtt, Mqtt\nJSON: json' } });
    fireEvent.change(screen.getByLabelText(/Wordy phrases/), { target: { value: 'utilise => use' } });
    fireEvent.click(screen.getByText('Use Vale'));
    fireEvent.click(screen.getByText('Save settings'));
    await waitFor(() => expect(api.lint.saveConfig).toHaveBeenCalled());
    const sent = api.lint.saveConfig.mock.calls[0][0];
    expect(sent.glossary).toEqual({ MQTT: ['mqtt', 'Mqtt'], JSON: ['json'] });
    expect(sent.redundant_phrases).toEqual({ utilise: 'use' });
  });

  it('shows the settings but not the save button to everyone else', async () => {
    render(<AppProvider><As permissions={['read', 'write']}><WritingCheckPanel onClose={() => {}} /></As></AppProvider>);
    fireEvent.click(await screen.findByText('Settings (read only)'));
    await screen.findByText(/Only an administrator can change these settings/);
    expect(screen.queryByText('Save settings')).toBeNull();
    expect(screen.getByTestId('vale-status')).toHaveTextContent('Vale was not found');
  });
});

describe('WritingStrip', () => {
  it('shows nothing when the item is clean', async () => {
    api.requirements.lint.mockResolvedValue({ enabled: true, issues: [] });
    const { container } = render(<AppProvider><WritingStrip uid="u1" version="1" /></AppProvider>);
    await waitFor(() => expect(api.requirements.lint).toHaveBeenCalled());
    expect(container.querySelector('[data-testid="writing-strip"]')).toBeNull();
  });

  it('counts the suggestions and expands to list them', async () => {
    api.requirements.lint.mockResolvedValue({ enabled: true, issues: report.issues });
    render(<AppProvider><WritingStrip uid="u1" version="1" /></AppProvider>);
    const toggle = await screen.findByText(/1 writing suggestion/);
    expect(screen.queryByText('Redundant phrase')).toBeNull();
    fireEvent.click(toggle);
    expect(screen.getByText('Redundant phrase')).toBeInTheDocument();
  });
});
