/**
 * App.jsx -- Root component.
 * Startup data, the page address (#372), the left-hand menu and area pages (#373), theme, Ctrl+K, and the
 * drawers for quick tasks (#374).
 */

import ErrorBoundary from './components/ErrorBoundary.jsx';
import { useEffect, useRef, useState, useCallback } from 'react';
import { AppProvider, useApp } from './AppContext';
import Header from './components/Header';
import Nav from './components/Nav';
import AreaPage from './components/Areas';
import { HelpPanel } from './components/Help';
import { ValidationPanel, ExportPanel } from './components/Panels';
import { BulkUpdatePanel, GlobalCommitModal } from './components/Tools';
import { ImportPanel, CmdPalette, WorkflowPanel } from './components/Advanced';
import { LoginModal } from './components/LoginModal';
import { InboxPanel } from './components/Insight';
import { api } from './api';
import { createAndOpen, templateBody } from './createItem';
import { buildRoute, parseRoute, rememberedProduct, rememberProduct } from './route';
import './index.css';

function AppShell() {
  const { state, dispatch, toast } = useApp();
  const { toasts } = state;
  const [gitStatus, setGitStatus] = useState(null);

  const toggle = useCallback((key, val = true) =>
    dispatch({ type: 'TOGGLE_PANEL', key, value: val }), [dispatch]);

  // Server answered 401: show the login dialog.
  useEffect(() => {
    const onUnauthorized = () => toggle('_showLogin');
    window.addEventListener('reqtool:unauthorized', onUnauthorized);
    return () => window.removeEventListener('reqtool:unauthorized', onUnauthorized);
  }, [toggle]);

  // ── Startup: load all data ──────────────────────────────────────────────
  useEffect(() => {
    Promise.all([
      api.products.list(),
      api.enums.all(),
      api.config.get(),
      api.workflow.get().catch(() => null),
      api.permissions().catch(() => null),
      api.hierarchy.get().catch(() => null),
      api.templates.list().catch(() => []),
      api.customFields.schema().catch(() => []),
    ]).then(([products, enums, config, workflow, permissions, hierarchy, templates, customFieldSchema]) => {
      dispatch({ type: 'SET_PRODUCTS',  payload: products });
      dispatch({ type: 'SET_ENUMS',     payload: { ...enums, _customFieldSchema: customFieldSchema, _current_user: localStorage.getItem('reqtool:username') || 'user' } });
      dispatch({ type: 'SET_WORKFLOW',  payload: workflow });
      if (permissions) dispatch({ type: 'SET_PERMISSIONS', payload: permissions });
      dispatch({ type: 'SET_HIERARCHY', payload: hierarchy });
      dispatch({ type: 'SET_TEMPLATES', payload: templates });

      // Active product: the one in the address, else the last one used here, else the configured default,
      // else the only one (#372).
      repoId.current = config?.repo_id || '';
      const wanted = state.routeProduct || rememberedProduct(repoId.current) || config?.ui?.default_product;
      const p = products.find(x => x.id === wanted) || (products.length === 1 ? products[0] : null);
      if (p) dispatch({ type: 'SET_ACTIVE_PRODUCT', payload: p, keepSelection: true });
      productsReady.current = true;

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

  // ── Page address (#372): the state writes the address; Back, Forward and pasted links write the state ──
  const repoId = useRef('');
  const productsReady = useRef(false);
  const last = useRef(null);
  useEffect(() => {
    const route = { area: state.area, tab: state.tab, item: state.selectedUid, type: state.selectedType,
      editorTab: state.editorTab, product: state.activeProduct?.id || (productsReady.current ? null : state.routeProduct) };
    const hash = buildRoute(route);
    const url = `${window.location.pathname}${hash}`;
    if (window.location.search || !last.current) {
      window.history.replaceState({}, '', url);           // first load, or an old ?uid= link: no extra history entry
    } else if (hash !== window.location.hash) {
      const prev = last.current;
      const newPage = prev.area !== route.area || prev.tab !== route.tab || prev.item !== route.item;
      if (newPage) window.history.pushState({}, '', url); else window.history.replaceState({}, '', url);
    }
    last.current = route;
  }, [state.area, state.tab, state.selectedUid, state.selectedType, state.editorTab, state.activeProduct?.id]);
  useEffect(() => {
    const onPop = () => {
      const route = parseRoute(window.location.hash, '');
      last.current = { ...route, product: route.product };
      dispatch({ type: 'ROUTE', route });
      if (route.product && route.product !== state.activeProduct?.id) {
        const p = state.products.find(x => x.id === route.product);
        if (p) dispatch({ type: 'SET_ACTIVE_PRODUCT', payload: p, keepSelection: true });
      }
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, [state.products, state.activeProduct?.id]);
  useEffect(() => {
    if (productsReady.current) rememberProduct(repoId.current, state.activeProduct?.id);
  }, [state.activeProduct?.id]);
  const [menuOpen, setMenuOpen] = useState(false);

  // ── Global Ctrl+K and ? ──────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        toggle('_showCmdPalette', !state._showCmdPalette);
      }
      if (e.key === 'Escape' && state._showCmdPalette) {
        toggle('_showCmdPalette', false);
      }
      // ? key opens help (when not typing in an input)
      if (e.key === '?' && !['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)) {
        toggle('_showHelp', !state._showHelp);
      }
      // Escape closes the editor drawer on pages that show it beside the content
      if (e.key === 'Escape' && state.selectedUid && !document.querySelector('[role="dialog"]')
          && !(state.area === 'requirements' && state.tab === 'tree') && state.area !== 'decisions'
          && !(state.area === 'principles' && state.tab === 'library')) {
        dispatch({ type: 'DESELECT' });
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [state._showCmdPalette, state._showHelp, state.selectedUid, state.area, state.tab, toggle]);

  const handleGlobalCommitDone = () => {
    api.git.status().then(setGitStatus).catch(() => {});
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Header
        onHelp={() => toggle('_showHelp')}
        onLogin={() => toggle('_showLogin')}
        onInbox={() => toggle('_showInbox')}
        onSearch={() => toggle('_showCmdPalette')}
        onMenu={() => setMenuOpen(o => !o)}
        onGlobalCommit={(status) => { setGitStatus(status); toggle('_showGlobalCommit'); }}
      />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden', minHeight: 0 }}>
        <Nav open={menuOpen} onClose={() => setMenuOpen(false)} />
        <ErrorBoundary scope="page" onReset={() => dispatch({ type: 'NAVIGATE', area: state.area })}>
          <AreaPage open={(key) => toggle(key)} />
        </ErrorBoundary>
      </div>

      {/* Drawers for quick tasks: a crash in one closes them instead of blanking the app */}
      <ErrorBoundary scope="panel" onReset={() => dispatch({ type: 'CLOSE_PANELS' })}>
      {state._showInbox        && <InboxPanel        onClose={() => toggle('_showInbox',        false)} />}
      {state._showLogin        && <LoginModal        onClose={() => toggle('_showLogin',        false)} />}
      {state._showHelp         && <HelpPanel initialTab="about"
        onClose={() => toggle('_showHelp', false)}
        onApplyTemplate={async t => { const item = await createAndOpen(templateBody(t), { dispatch, toast, hasProduct: !!state.activeProduct }); if (item) toggle('_showHelp', false); }} />}
      {state._showValidation   && <ValidationPanel   onClose={() => toggle('_showValidation',   false)} />}
      {state._showExport       && <ExportPanel        onClose={() => toggle('_showExport',        false)} />}
      {state._showBulk         && <BulkUpdatePanel    onClose={() => toggle('_showBulk',         false)} onDone={handleGlobalCommitDone} />}
      {state._showWorkflow     && <WorkflowPanel      onClose={() => toggle('_showWorkflow',     false)} />}
      {state._showImport       && <ImportPanel        onClose={() => toggle('_showImport',       false)} onDone={() => window.location.reload()} />}
      {state._showCmdPalette   && (
        <CmdPalette
          onClose={() => toggle('_showCmdPalette', false)}
          onSelect={(uid, type) => {
            // Open the item in its own area: decisions and principles have theirs; the rest open where you are.
            if (type === 'decision' || type === 'tbd') dispatch({ type: 'NAVIGATE', area: 'decisions', uid, artefactType: 'decision' });
            else if (type === 'principle') dispatch({ type: 'NAVIGATE', area: 'principles', tab: 'library', uid, artefactType: 'principle' });
            else dispatch({ type: 'SELECT', uid, artefactType: type });
            toggle('_showCmdPalette', false);
          }}
          onNavigate={(area, tab) => { dispatch({ type: 'NAVIGATE', area, tab }); toggle('_showCmdPalette', false); }}
        />
      )}
      {state._showGlobalCommit && (
        <GlobalCommitModal
          staged={gitStatus?.staged || []}
          onClose={() => toggle('_showGlobalCommit', false)}
          onDone={handleGlobalCommitDone}
        />
      )}
      </ErrorBoundary>

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
