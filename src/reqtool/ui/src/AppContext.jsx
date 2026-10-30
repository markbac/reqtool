/**
 * AppContext.jsx
 * Global state: products, selection, enums, workflow, templates, panels, theme, toasts.
 */

import { createContext, useContext, useReducer, useMemo } from 'react';

const initialState = {
  products: [], activeProduct: null, activeVariant: null,
  enums: {}, workflow: null, hierarchy: null, templates: [],
  permissions: null, role: null, operatingMode: null,
  selectedUid: null, selectedType: null,
  panel: 'requirements',
  dirtyUids: new Set(),
  searchQuery: '',
  _showValidation: false, _showExport: false, _showCoverage: false,
  _showBulk: false, _showGlobalCommit: false, _showVocabularies: false,
  _showBaselines: false, _showMetrics: false, _showImport: false,
  _showWorkflow: false, _showTemplates: false, _showTraceability: false,
  _showCmdPalette: false, _showCustomFields: false, _showWebhooks: false,
  _showHelp: false, _showWorkflowEditor: false, _showWritingCheck: false,
  _lastCommit: 0,
  theme: 'dark',
  toasts: [],
};

function reducer(state, action) {
  switch (action.type) {
    case 'SET_PRODUCTS':      return { ...state, products: action.payload };
    case 'SET_ACTIVE_PRODUCT':return { ...state, activeProduct: action.payload, selectedUid: null };
    case 'SET_ACTIVE_VARIANT':return { ...state, activeVariant: action.payload };
    case 'SET_ENUMS':         return { ...state, enums: action.payload };
    case 'SET_WORKFLOW':      return { ...state, workflow: action.payload };
    case 'SET_HIERARCHY':     return { ...state, hierarchy: action.payload };
    case 'SET_PERMISSIONS':   return { ...state, permissions: action.payload.permissions, role: action.payload.role,
                                       operatingMode: action.payload.operating_mode ?? null };
    case 'SET_TEMPLATES':     return { ...state, templates: action.payload };
    case 'SELECT':            return { ...state, selectedUid: action.uid, selectedType: action.artefactType };
    case 'DESELECT':          return { ...state, selectedUid: null, selectedType: null };
    case 'SET_PANEL':         return { ...state, panel: action.payload, selectedUid: null, selectedType: null };
    case 'MARK_DIRTY': {
      return { ...state, dirtyUids: new Set([...state.dirtyUids, action.uid]) };
    }
    case 'MARK_CLEAN': {
      const next = new Set(state.dirtyUids); next.delete(action.uid);
      return { ...state, dirtyUids: next };
    }
    case 'SET_THEME':     return { ...state, theme: action.payload };
    case 'SET_SEARCH':    return { ...state, searchQuery: action.payload };
    case 'COMMITTED':     return { ...state, _lastCommit: Date.now() };
    case 'TOGGLE_PANEL':  return { ...state, [action.key]: action.value };
    case 'CLOSE_PANELS':  return Object.fromEntries(Object.entries(state).map(([k, v]) => [k, k.startsWith('_show') ? false : v]));
    case 'TOAST_ADD':     return { ...state, toasts: [...state.toasts, action.payload] };
    case 'TOAST_REMOVE':  return { ...state, toasts: state.toasts.filter(t => t.id !== action.id) };
    default: return state;
  }
}

const AppContext = createContext(null);

let toastSeq = 0;

export function AppProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const toast = useMemo(() => {
    const fn = (message, kind = 'info', duration = 3000) => {
      const id = ++toastSeq;
      dispatch({ type: 'TOAST_ADD', payload: { id, message, kind } });
      setTimeout(() => dispatch({ type: 'TOAST_REMOVE', id }), duration);
    };
    // Convenience helpers: toast.success(msg), toast.error(msg), ...
    for (const kind of ['success', 'error', 'info', 'warn']) {
      fn[kind] = (message, duration) => fn(message, kind, duration);
    }
    return fn;
  }, []);
  return (
    <AppContext.Provider value={{ state, dispatch, toast }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  return useContext(AppContext);
}

/**
 * can(action): whether the signed-in role may do ``action`` (read, write, delete, manage_workflow, manage_lint,
 * manage_config, manage_repo, manage_modules, manage_webhooks, manage_users). The server is what enforces this;
 * the UI only hides what would be refused. Until /permissions has answered everything is shown.
 */
export function useCan() {
  const { state } = useContext(AppContext);
  const granted = state.permissions;
  return (action) => granted === null || granted === undefined || granted.includes(action);
}
