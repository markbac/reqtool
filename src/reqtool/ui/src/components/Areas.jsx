/**
 * Areas.jsx -- The six areas of the left-hand menu (#373). Each is a page with tabs; the tab is in the address
 * (#372). Screens that used to open from the More menu render here as pages (#374). Where a page has no editor
 * column of its own, a selected item opens in the editor drawer on the right.
 */

import { useState } from 'react';
import { useApp, useCan } from '../AppContext';
import { InPage } from './Advanced/Panel';
import Editor from './Editor';
import { RequirementsPanel, DecisionsList } from './Sidebar';
import { PrinciplesPanel } from './Principles';
import { KanbanPanel } from './Kanban';
import { ViewsPanel } from './Views';
import { CoveragePanel, VocabulariesPanel } from './Tools';
import {
  BaselinesPanel, MetricsPanel, TraceabilityPanel, TemplatesPanel, CustomFieldsPanel, WebhooksPanel,
  AutomationRulesPanel, DuplicateDetectorPanel,
} from './Advanced';
import { WorkflowEditor } from './WorkflowEditor';
import { WritingCheckPanel } from './WritingCheck';
import { RepoModal } from './RepoModal';
import { DiagramPanel } from './DiagramPanel';
import { IterationsPanel } from './IterationsPanel';
import { OverviewPanel, RoadmapPanel, ModulesPanel, ChangeSetsPanel, QueryPanel, DecisionsPanel } from './Insight';
import { BacklogPage, IssuesPage } from './Work';
import './Areas.css';

const stay = () => {};   // a page does not close

const TABS = {
  requirements: [['tree', 'Tree'], ['table', 'Query'], ['modules', 'Modules'], ['baselines', 'Baselines'], ['changesets', 'Change sets']],
  work: [['issues', 'Issues'], ['backlog', 'Backlog'], ['tree', 'Tree'], ['board', 'Board'], ['roadmap', 'Roadmap'], ['iterations', 'Iterations']],
  decisions: [['', 'List'], ['records', 'Options and ADRs']],
  principles: [['library', 'Library'], ['cited', 'Where cited']],
  insights: [['overview', 'Overview'], ['coverage', 'Coverage'], ['traceability', 'Traceability'], ['views', 'Views'], ['diagrams', 'Diagrams']],
  settings: [['workflows', 'Workflows'], ['fields', 'Custom fields', 'manage_config'], ['vocabularies', 'Vocabularies', 'manage_config'],
    ['templates', 'Templates', 'manage_config'], ['automation', 'Automation'], ['webhooks', 'Webhooks', 'manage_webhooks'],
    ['writing', 'Writing check'], ['repository', 'Repository', 'manage_repo']],
};

/** The tabs of an area this role may use: a settings tab the role cannot change is left out, as the old menu did. */
function tabsFor(area, can) {
  return (TABS[area] || []).filter(([, , need]) => !need || can(need));
}
const TITLES = { requirements: 'Requirements', work: 'Work', decisions: 'Decisions', principles: 'Principles',
  insights: 'Insights', settings: 'Settings' };

function PageHeader({ area, actions, badges = {} }) {
  const { state, dispatch } = useApp();
  const can = useCan();
  const tabs = tabsFor(area, can);
  return (
    <div className="page-head">
      <div className="page-title-row">
        <h1 className="page-title">{TITLES[area]}</h1>
        {state.activeProduct && <span className="page-context">{state.activeProduct.title || state.activeProduct.id}</span>}
        {actions && <div className="page-actions">{actions}</div>}
      </div>
      {tabs.length > 0 && (
        <div className="page-tabs" role="tablist" aria-label={`${TITLES[area]} views`}>
          {tabs.map(([id, label]) => (
            <a key={id || 'list'} role="tab" href={`#/${area}${id ? `/${id}` : ''}`} aria-selected={state.tab === id}
              className={`page-tab ${state.tab === id ? 'page-tab--on' : ''}`}
              onClick={e => { e.preventDefault(); dispatch({ type: 'NAVIGATE', area, tab: id }); }}>
              {label}{badges[id] ? <span className="page-tab-count">{badges[id]}</span> : null}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

/** A page with an editor drawer for whatever is selected. */
function WithEditorDrawer({ children }) {
  const { state, dispatch } = useApp();
  return (
    <div className="page-with-drawer">
      <div className="page-content"><InPage>{children}</InPage></div>
      {state.selectedUid && (
        <aside className="editor-drawer" aria-label="Editor">
          <div className="editor-drawer-head">
            <span>Editing</span>
            <button className="btn btn-ghost" aria-label="Close editor" onClick={() => dispatch({ type: 'DESELECT' })}>✕</button>
          </div>
          <div className="editor-drawer-body"><Editor /></div>
        </aside>
      )}
    </div>
  );
}

/** A list or tree on the left and the editor on the right. */
function ListAndEditor({ list, label }) {
  return (
    <div className="page-split">
      <section className="page-list" aria-label={label}>{list}</section>
      <main className="page-editor"><Editor /></main>
    </div>
  );
}

function CheckMenu() {
  const { dispatch } = useApp();
  const [open, setOpen] = useState(false);
  const go = (tab) => { setOpen(false); dispatch({ type: 'NAVIGATE', area: 'requirements', tab }); };
  return (
    <div className="page-menu">
      <button className="btn btn-secondary" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(o => !o)}>Check ▾</button>
      {open && (
        <div className="page-menu-list" role="menu">
          <button role="menuitem" onClick={() => go('writing')}>Writing check</button>
          <button role="menuitem" onClick={() => go('duplicates')}>Duplicates</button>
        </div>
      )}
    </div>
  );
}

function RequirementsArea({ open }) {
  const { state } = useApp();
  const can = useCan();
  const actions = <>
    <button className="btn btn-secondary" onClick={() => open('_showValidation')}>Validate</button>
    <button className="btn btn-secondary" onClick={() => open('_showExport')}>Export</button>
    {can('write') && <button className="btn btn-secondary" onClick={() => open('_showImport')}>Import</button>}
    {can('write') && <button className="btn btn-secondary" onClick={() => open('_showBulk')}>Bulk edit</button>}
    <CheckMenu />
  </>;
  const tab = state.tab;
  return (
    <div className="area">
      <PageHeader area="requirements" actions={actions} />
      {tab === 'tree' && <ListAndEditor label="Requirement tree" list={<RequirementsPanel family="requirement" />} />}
      {tab === 'table' && <WithEditorDrawer><QueryPanel onClose={stay} /></WithEditorDrawer>}
      {tab === 'modules' && <WithEditorDrawer><ModulesPanel onClose={stay} /></WithEditorDrawer>}
      {tab === 'baselines' && <WithEditorDrawer><BaselinesPanel onClose={stay} /></WithEditorDrawer>}
      {tab === 'changesets' && <WithEditorDrawer><ChangeSetsPanel onClose={stay} /></WithEditorDrawer>}
      {tab === 'writing' && <WithEditorDrawer><WritingCheckPanel onClose={stay} /></WithEditorDrawer>}
      {tab === 'duplicates' && <WithEditorDrawer><DuplicateDetectorPanel onClose={stay} /></WithEditorDrawer>}
    </div>
  );
}

function WorkArea({ open }) {
  const { state } = useApp();
  const can = useCan();
  const actions = can('write') ? <>
    <button className="btn btn-secondary" onClick={() => open('_showImport')}>Import</button>
    <button className="btn btn-secondary" onClick={() => open('_showBulk')}>Bulk edit</button>
  </> : null;
  const tab = state.tab;
  return (
    <div className="area">
      <PageHeader area="work" actions={actions} />
      {tab === 'issues' && <IssuesPage />}
      {tab === 'backlog' && <BacklogPage />}
      {tab === 'tree' && <ListAndEditor label="Work tree" list={<RequirementsPanel family="work" />} />}
      {tab === 'board' && <WithEditorDrawer><KanbanPanel /></WithEditorDrawer>}
      {tab === 'roadmap' && <WithEditorDrawer><RoadmapPanel onClose={stay} /></WithEditorDrawer>}
      {tab === 'iterations' && <WithEditorDrawer><IterationsPanel onClose={stay} /></WithEditorDrawer>}
    </div>
  );
}

function DecisionsArea() {
  const { state } = useApp();
  return (
    <div className="area">
      <PageHeader area="decisions" />
      {state.tab === 'records'
        ? <WithEditorDrawer><DecisionsPanel onClose={stay} /></WithEditorDrawer>
        : <ListAndEditor label="Decision list" list={<DecisionsList />} />}
    </div>
  );
}

function PrinciplesArea() {
  const { state } = useApp();
  return (
    <div className="area">
      <PageHeader area="principles" />
      {state.tab === 'library' && <ListAndEditor label="Principle library" list={<PrinciplesPanel />} />}
      {state.tab === 'cited' && <WithEditorDrawer><ViewsPanel onClose={stay} initial="principles" only /></WithEditorDrawer>}
    </div>
  );
}

function InsightsArea({ open }) {
  const { state } = useApp();
  const actions = <>
    <button className="btn btn-secondary" onClick={() => open('_showValidation')}>Validate now</button>
    <button className="btn btn-secondary" onClick={() => open('_showExport')}>Export</button>
  </>;
  return (
    <div className="area">
      <PageHeader area="insights" actions={actions} />
      {state.tab === 'overview' && <WithEditorDrawer><OverviewPanel onClose={stay} /><MetricsPanel onClose={stay} /></WithEditorDrawer>}
      {state.tab === 'coverage' && <WithEditorDrawer><CoveragePanel onClose={stay} /></WithEditorDrawer>}
      {state.tab === 'traceability' && <WithEditorDrawer><TraceabilityPanel onClose={stay} /></WithEditorDrawer>}
      {state.tab === 'views' && <WithEditorDrawer><ViewsPanel onClose={stay} /></WithEditorDrawer>}
      {state.tab === 'diagrams' && <WithEditorDrawer><DiagramPanel onClose={stay} /></WithEditorDrawer>}
    </div>
  );
}

function SettingsArea() {
  const { state } = useApp();
  const can = useCan();
  // a tab this role may not use (an old link, say) shows the first one it may
  const tab = tabsFor('settings', can).some(([id]) => id === state.tab) ? state.tab : 'workflows';
  return (
    <div className="area">
      <PageHeader area="settings" />
      <WithEditorDrawer>
        {tab === 'workflows' && <WorkflowEditor onClose={stay} />}
        {tab === 'fields' && <CustomFieldsPanel onClose={stay} />}
        {tab === 'vocabularies' && <VocabulariesPanel onClose={stay} />}
        {tab === 'templates' && <TemplatesPanel onClose={stay} />}
        {tab === 'automation' && <AutomationRulesPanel onClose={stay} />}
        {tab === 'webhooks' && <WebhooksPanel onClose={stay} />}
        {tab === 'writing' && <WritingCheckPanel onClose={stay} initialTab="settings" />}
        {tab === 'repository' && <RepoModal onClose={stay} />}
      </WithEditorDrawer>
    </div>
  );
}

export default function AreaPage({ open }) {
  const { state } = useApp();
  switch (state.area) {
    case 'work': return <WorkArea open={open} />;
    case 'decisions': return <DecisionsArea />;
    case 'principles': return <PrinciplesArea />;
    case 'insights': return <InsightsArea open={open} />;
    case 'settings': return <SettingsArea />;
    default: return <RequirementsArea open={open} />;
  }
}
