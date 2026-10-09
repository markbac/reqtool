let behave = 'ok';
vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async () => {
      if (behave === 'fail') throw new Error('parse error');
      return { svg: '<svg data-testid="drawn"></svg>' };
    }),
  },
}));

import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MermaidView } from '../components/MermaidView.jsx';

describe('MermaidView', () => {
  it('draws the diagram the server made', async () => {
    behave = 'ok';
    render(<MermaidView source={'flowchart LR\n a --> b'} />);
    await waitFor(() => expect(screen.getByTestId('mermaid-diagram').innerHTML).toContain('<svg'));
  });
  it('falls back to the source text when it cannot be drawn', async () => {
    behave = 'fail';
    render(<MermaidView source={'flowchart LR\n a --> b'} />);
    expect(await screen.findByTestId('mermaid-source')).toHaveTextContent('a --> b');
  });
  it('renders nothing without a source', () => {
    const { container } = render(<MermaidView source="" />);
    expect(container).toBeEmptyDOMElement();
  });
});
