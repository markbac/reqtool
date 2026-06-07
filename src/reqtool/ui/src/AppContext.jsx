/**
 * AppContext.jsx
 * Global state: products, selection, enums, workflow, templates, panels, theme, toasts.
 */

import { createContext, useContext, useReducer, useCallback } from 'react';

const initialState = {
  products: [], activeProduct: null, activeVariant: null,
  enums: {}, workflow: null, templates: [],
  selectedUid: null, selectedType: null,
  panel: 'requirements',
  dirtyUids: new Set(),
  searchQuery: '',
  _showValidation: false, _showExport: false, _showCoverage: false,
  _showBulk: false, _showGlobalCommit: false, _showVocabularies: false,
  _showBaselines: false, _showMetrics: false, _showImport: false,
  _showWorkflow: false, _showTemplates: false, _showTraceability: false,
  _showCmdPalette: false, _showCustomFields: false, _showWebhooks: false,
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
    case 'TOAST_ADD':     return { ...state, toasts: [...state.toasts, action.payload] };
    case 'TOAST_REMOVE':  return { ...state, toasts: state.toasts.filter(t => t.id !== action.id) };
    default: return state;
  }
}

const AppContext = createContext(null);

let toastSeq = 0;

export function AppProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const toast = useCallback((message, kind = 'info', duration = 3000) => {
    const id = ++toastSeq;
    dispatch({ type: 'TOAST_ADD', payload: { id, message, kind } });
    setTimeout(() => dispatch({ type: 'TOAST_REMOVE', id }), duration);
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
