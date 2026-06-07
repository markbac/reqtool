import '@testing-library/jest-dom';

// Mock @uiw/react-codemirror -- it pulls in a separate React copy in jsdom
// which breaks useContext. In tests we just need a plain textarea.
vi.mock('@uiw/react-codemirror', () => ({
  default: ({ value, onChange, ...props }) => (
    <textarea
      data-testid="codemirror-mock"
      value={value || ''}
      onChange={e => onChange && onChange(e.target.value)}
    />
  ),
}));
