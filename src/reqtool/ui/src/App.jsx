/**
 * App.jsx -- Root component.
 * Handles: startup data loading, deep-link routing, theme persistence,
 * global Ctrl+K command palette, and all overlay panel wiring.
 */

import { useEffect, useState, useCallback } from 'react';
import { AppProvider, useApp } from './AppContext';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import Editor from './components/Editor';
import { ValidationPanel, ExportPanel } from './components/Panels';
import {
  CoveragePanel, BulkUpdatePanel, GlobalCommitModal, VocabulariesPanel,
} from './components/Tools';
import {
  BaselinesPanel, MetricsPanel, ImportPanel,
  TraceabilityPanel, CmdPalette, WorkflowPanel, TemplatesPanel,
  CustomFieldsPanel, WebhooksPanel,
} from './components/Advanced';
import { api } from './api';
import './index.css';

function AppShell() {
  const { state, dispatch, toast } = useApp();
  const { toasts } = state;
  const [gitStatus, setGitStatus] = useState(null);

  const toggle = useCallback((key, val = true) =>
    dispatch({ type: 'TOGGLE_PANEL', key, value: val }), [dispatch]);

  // ── Startup: load all data ──────────────────────────────────────────────
  useEffect(() => {
    Promise.all([
      api.products.list(),
      api.enums.all(),
      api.config.get(),
      api.workflow.get().catch(() => null),
      api.templates.list().catch(() => []),
      api.customFields.schema().catch(() => []),
    ]).then(([products, enums, config, workflow, templates, customFieldSchema]) => {
      dispatch({ type: 'SET_PRODUCTS',  payload: products });
      dispatch({ type: 'SET_ENUMS',     payload: { ...enums, _customFieldSchema: customFieldSchema, _current_user: localStorage.getItem('reqtool:username') || 'user' } });
      dispatch({ type: 'SET_WORKFLOW',  payload: workflow });
      dispatch({ type: 'SET_TEMPLATES', payload: templates });

      // Active product
      const defaultId = config?.ui?.default_product;
      if (defaultId) {
        const p = products.find(p => p.id === defaultId);
        if (p) dispatch({ type: 'SET_ACTIVE_PRODUCT', payload: p });
      } else if (products.length === 1) {
        dispatch({ type: 'SET_ACTIVE_PRODUCT', payload: products[0] });
      }

      // Theme -- prefer localStorage over config
      const savedTheme = localStorage.getItem('reqtool:theme');
      const theme = savedTheme || config?.ui?.theme || 'dark';
      dispatch({ type: 'SET_THEME', payload: theme });
      document.documentElement.setAttribute('data-theme', theme);
      document.documentElement.style.colorScheme = theme;
    }).catch(err => {
      toast('Could not connect to reqtool server: ' + err.message, 'error', 8000);
    });
  }, []);

  // ── Deep linking: read ?uid= from URL on load ────────────────────────────
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const uid = params.get('uid');
    const type = params.get('type') || 'requirement';
    if (uid) {
      dispatch({ type: 'SELECT', uid, artefactType: type });
    }
  }, []);

  // ── Deep linking: write ?uid= to URL on selection ───────────────────────
  useEffect(() => {
    const { selectedUid, selectedType } = state;
    const url = new URL(window.location.href);
    if (selectedUid) {
      url.searchParams.set('uid', selectedUid);
      url.searchParams.set('type', selectedType || 'requirement');
    } else {
      url.searchParams.delete('uid');
      url.searchParams.delete('type');
    }
    window.history.replaceState({}, '', url.toString());
  }, [state.selectedUid, state.selectedType]);

  // ── Global Ctrl+K ────────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        toggle('_showCmdPalette', !state._showCmdPalette);
      }
      if (e.key === 'Escape' && state._showCmdPalette) {
        toggle('_showCmdPalette', false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [state._showCmdPalette, toggle]);

  const handleGlobalCommitDone = () => {
    api.git.status().then(setGitStatus).catch(() => {});
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Header
        onValidate={() => toggle('_showValidation')}
        onExport={() => toggle('_showExport')}
        onCoverage={() => toggle('_showCoverage')}
        onBulk={() => toggle('_showBulk')}
        onVocabularies={() => toggle('_showVocabularies')}
        onBaselines={() => toggle('_showBaselines')}
        onMetrics={() => toggle('_showMetrics')}
        onImport={() => toggle('_showImport')}
        onTraceability={() => toggle('_showTraceability')}
        onCustomFields={() => toggle('_showCustomFields')}
        onWebhooks={() => toggle('_showWebhooks')}
        onGlobalCommit={(status) => { setGitStatus(status); toggle('_showGlobalCommit'); }}
      />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <Sidebar />
        <main style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <Editor />
        </main>
      </div>

      {/* Overlay panels */}
      {state._showValidation   && <ValidationPanel   onClose={() => toggle('_showValidation',   false)} />}
      {state._showExport       && <ExportPanel        onClose={() => toggle('_showExport',        false)} />}
      {state._showCoverage     && <CoveragePanel      onClose={() => toggle('_showCoverage',     false)} />}
      {state._showBulk         && <BulkUpdatePanel    onClose={() => toggle('_showBulk',         false)} onDone={handleGlobalCommitDone} />}
      {state._showVocabularies && <VocabulariesPanel  onClose={() => toggle('_showVocabularies', false)} />}
      {state._showBaselines    && <BaselinesPanel     onClose={() => toggle('_showBaselines',    false)} />}
      {state._showMetrics      && <MetricsPanel       onClose={() => toggle('_showMetrics',      false)} />}
      {state._showImport       && <ImportPanel        onClose={() => toggle('_showImport',       false)} onDone={() => window.location.reload()} />}
      {state._showTraceability && <TraceabilityPanel  onClose={() => toggle('_showTraceability', false)} />}
      {state._showWorkflow     && <WorkflowPanel      onClose={() => toggle('_showWorkflow',     false)} />}
      {state._showTemplates    && <TemplatesPanel     onClose={() => toggle('_showTemplates',    false)} />}
      {state._showCustomFields && <CustomFieldsPanel  onClose={() => toggle('_showCustomFields', false)} />}
      {state._showWebhooks     && <WebhooksPanel      onClose={() => toggle('_showWebhooks',     false)} />}
      {state._showCmdPalette   && (
        <CmdPalette
          onClose={() => toggle('_showCmdPalette', false)}
          onSelect={(uid, type) => {
            dispatch({ type: 'SELECT', uid, artefactType: type });
            toggle('_showCmdPalette', false);
          }}
        />
      )}
      {state._showGlobalCommit && (
        <GlobalCommitModal
          staged={gitStatus?.staged || []}
          onClose={() => toggle('_showGlobalCommit', false)}
          onDone={handleGlobalCommitDone}
        />
      )}

      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast toast-${t.kind}`}>{t.message}</div>
        ))}
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <AppShell />
    </AppProvider>
  );
}
