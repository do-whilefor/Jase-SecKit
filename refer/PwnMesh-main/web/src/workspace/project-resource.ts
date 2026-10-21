import { APIError, Client, RequestScope } from '../api/client';
import type { APIClient, RequestOptions } from '../api/client';
import type { ExecutionDTO, InputDTO, ProjectDTO, StateEventDTO, WorkspaceSnapshot } from '../api/types';
import { buildLogs, projectTiming } from './model/data';
import type { ProjectStatus, ProjectView } from './model/types';

export const pathFor = (id: string): string => '/projects/' + encodeURIComponent(id);
const statuses: Record<string, ProjectStatus> = {active: 'running', stopped: 'paused', completed: 'done', terminated: 'terminated'};
export function projectView(raw: ProjectDTO, previous: Partial<ProjectView> = {}): ProjectView {
  return {...previous, id: raw.id, name: raw.title, type: raw.scenario || '', status: statuses[raw.status] || 'pending', readOnly: raw.orchestration_version !== 1,
    generation: raw.generation || 0, createdAt: raw.created_at, endedAt: raw.terminated_at || previous.endedAt || null, target: previous.target || '', goal: previous.goal || '',
    files: previous.files || [], history: [], state: previous.state || null, logs: previous.logs || [], raw};
}
export function snapshotView(state: WorkspaceSnapshot, events: StateEventDTO[] = [], runs: ExecutionDTO[] = [], files: InputDTO[] = [], previous: Partial<ProjectView> = {}): ProjectView {
  const project = projectView(state.graph.project, previous), facts = state.graph.facts || [];
  const timing = projectTiming(state, runs);
  return {...project, state, logs: buildLogs(state, events, runs), runs, events, files, filesKnown: true, target: facts.find(f => f.id === 'origin')?.description || '',
    goal: facts.find(f => f.id === 'goal')?.description || state.goals?.find(g => g.id === 'goal')?.condition || '', startedAt: timing.startedAt, endedAt: timing.endedAt || null};
}
interface EventCache { generation: number; revision: number; after: number; caughtUp: boolean; items: StateEventDTO[] }
interface ReadView { generation: number; summary: string; state: WorkspaceSnapshot; runs: ExecutionDTO[]; files: InputDTO[]; executionRevision: number }
export interface RefreshResult { projects: readonly ProjectView[]; selected: ProjectView | undefined }
async function readEventCache(api: APIClient, base: string, state: WorkspaceSnapshot, previous: EventCache | undefined, options: RequestOptions): Promise<EventCache> {
  const generation = state.graph.project.generation || 0, revision = state.revision;
  const cache: EventCache = !previous || previous.generation !== generation || revision < previous.revision
    ? {generation, revision: 0, after: 0, items: [], caughtUp: false} : previous;
  if (cache.caughtUp && cache.revision === revision) return cache;
  const batch: StateEventDTO[] = [];
  let after = cache.after, caughtUp = false;
  // A bounded refresh continues an unfinished backlog even when state is unchanged.
  for (let page = 0; page < 5; page++) {
    const items = await api.request<StateEventDTO[]>(base + '/state/events?after=' + after, options);
    if (!items.length) { caughtUp = true; break; }
    const next = Math.max(...items.map(event => event.revision));
    if (next <= after) { caughtUp = true; break; }
    batch.push(...items); after = next;
    if (items.length < 1000) { caughtUp = true; break; }
  }
  return {generation, revision, after, caughtUp, items: batch.length ? cache.items.concat(batch) : cache.items};
}

/** Sole owner of accepted workspace reads; Vue owns only the refresh schedule. */
export class ProjectResource {
  readonly scope = new RequestScope();
  private accepted: ProjectView[] = [];
  private readonly events = new Map<string, EventCache>();
  private readonly views = new Map<string, ReadView>();
  constructor(readonly api: APIClient = new Client()) {}
  get projects(): readonly ProjectView[] { return this.accepted; }
  cancel(): void { this.scope.cancel(); }
  invalidate(id: string): void { this.events.delete(id); this.views.delete(id); }
  async refresh(preferred = ''): Promise<RefreshResult | null> {
    const request = this.scope.begin(), options = {signal: request.signal};
    const list = await this.api.request<ProjectDTO[]>('/projects', options);
    if (!this.scope.current(request.version)) return null;
    const projects = list.map(raw => projectView(raw, raw.orchestration_version === 1 ? this.accepted.find(p => p.id === raw.id) : {filesKnown: false})).sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)) || b.id.localeCompare(a.id));
    const selected = projects.find(p => p.id === preferred) || projects[0];
    if (selected && !selected.readOnly) {
      const base = pathFor(selected.id), previous = this.views.get(selected.id), summary = JSON.stringify(selected.raw);
      const sameGeneration = previous?.generation === selected.generation;
      // Late execution cleanup can add data after a project reaches its terminal status.
      const terminal = ['done', 'terminated'].includes(selected.status), stableTerminal = sameGeneration && terminal && previous.summary === summary;
      const [loadedState, changes] = await Promise.all([
        stableTerminal ? previous.state : this.api.request<WorkspaceSnapshot>(base + '/state', options),
        this.api.executionChanges(base, sameGeneration ? previous.executionRevision : 0, selected.generation, options).catch((error: unknown) => {
          if (error instanceof APIError && error.status === 409 && this.scope.current(request.version)) this.invalidate(selected.id);
          throw error;
        }),
      ]);
      if (!this.scope.current(request.version)) return null;
      const state = terminal && (changes.items.length || changes.deleted.length) ? await this.api.request<WorkspaceSnapshot>(base + '/state', options) : loadedState;
      if (!this.scope.current(request.version)) return null;
      const generation = state.graph.project.generation || 0;
      const files = sameGeneration && state.revision === previous.state.revision ? previous.files : await this.api.request<InputDTO[]>(base + '/inputs', options);
      if (!this.scope.current(request.version)) return null;
      const runsByID = new Map((sameGeneration ? previous.runs : []).map(run => [run.id, run]));
      for (const id of changes.deleted) runsByID.delete(id);
      for (const run of changes.items) if ((run.generation || 0) === generation) runsByID.set(run.id, run);
      const runs = [...runsByID.values()], previousEvents = this.events.get(selected.id);
      const cache = await readEventCache(this.api, base, state, previousEvents, options);
      const identity = await this.api.request<{id: string; generation?: number}>(base + '/identity', options);
      if (!this.scope.current(request.version)) return null;
      // State/event revisions, execution cursors and project generations are different axes.
      if (selected.generation !== generation || (identity.generation || 0) !== generation) { this.invalidate(selected.id); throw new APIError('项目已重启，正在重新同步。', 409); }
      this.events.set(selected.id, cache);
      if (!stableTerminal || changes.items.length || changes.deleted.length || cache.items !== previousEvents?.items) Object.assign(selected, snapshotView(state, cache.items.filter(e => e.revision <= state.revision), runs, files, selected));
      this.views.set(selected.id, {generation, summary, state, runs, files, executionRevision: changes.through});
    }
    if (!this.scope.current(request.version)) return null;
    for (const id of this.views.keys()) if (!projects.some(project => project.id === id && !project.readOnly)) this.invalidate(id);
    this.accepted = projects;
    return {projects: this.accepted, selected};
  }
}
