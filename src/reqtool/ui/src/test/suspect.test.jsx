vi.mock('@uiw/react-codemirror', () => ({ default: () => null }));

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AppProvider } from '../AppContext';
import { RelationshipsEditor } from '../components/Editor.jsx';

const rels = [
  { type: 'derived_from', target: { uid: 'u1' }, _display: 'REQ-1 -- Upstream', suspect: true },
  { type: 'relates_to', target: { uid: 'u2' }, _display: 'REQ-2 -- Other' },
];

describe('suspect links (UI-03)', () => {
  it('flags only suspect rows and calls onClearSuspect with that link', () => {
    const onClear = vi.fn();
    render(<AppProvider><RelationshipsEditor rels={rels} onChange={() => {}} enums={{}} onClearSuspect={onClear} /></AppProvider>);
    expect(screen.getAllByText(/suspect/i).filter(e => e.className.split(' ').includes('rel-suspect'))).toHaveLength(1);
    expect(screen.getAllByText('Clear suspect')).toHaveLength(1);
    fireEvent.click(screen.getByText('Clear suspect'));
    expect(onClear).toHaveBeenCalledWith(rels[0]);
  });
  it('shows no suspect controls when nothing is suspect', () => {
    render(<AppProvider><RelationshipsEditor rels={[rels[1]]} onChange={() => {}} enums={{}} /></AppProvider>);
    expect(screen.queryByText('Clear suspect')).toBeNull();
  });
});
