/**
 * HIVE bridge — renderer side. Listens for ADD_TASK_FROM_API IPC events and
 * commits tasks through TaskService.add() so the addTask meta-reducer keeps
 * Task/Project/Tag state atomically consistent.
 *
 * NEW FILE → place at:  src/app/features/tasks/store/task-api.effects.ts
 * Register alongside TaskElectronEffects — see PATCHES.md §4.
 *
 * ⚠ Two version-sensitive spots are marked VERIFY below. Check them against
 *   your checkout before building (they're also in PATCHES.md).
 */
import { inject, Injectable } from '@angular/core';
import { createEffect } from '@ngrx/effects';
import { Observable, firstValueFrom } from 'rxjs';
import { TaskService } from '../task.service';
import { ProjectService } from '../../project/project.service';
import { TagService } from '../../tag/tag.service';
import { Task } from '../task.model';
import { IS_ELECTRON } from '../../../app.constants';
import { IPC } from '../../../../../electron/shared-with-frontend/ipc-events.const';

interface ExternalTaskPayload {
  title: string;
  notes?: string;
  projectId?: string;
  projectName?: string;
  tagNames?: string[];
  dueDay?: string;
  dueWithTime?: number;
  timeEstimate?: number;
  externalId?: string;
}

@Injectable()
export class TaskApiEffects {
  private _taskService = inject(TaskService);
  private _projectService = inject(ProjectService);
  private _tagService = inject(TagService);

  addTaskFromApi$ = createEffect(
    () =>
      new Observable<void>(() => {
        if (!IS_ELECTRON) {
          return;
        }
        window.ea.on(
          IPC.ADD_TASK_FROM_API,
          (_ev: unknown, payload: ExternalTaskPayload) => {
            this._handleAdd(payload).catch((e) =>
              console.error('[HIVE bridge]', e),
            );
          },
        );
      }),
    { dispatch: false },
  );

  private async _handleAdd(payload: ExternalTaskPayload): Promise<void> {
    const projectId = await this._resolveProjectId(payload);
    const tagIds = await this._resolveTagIds(payload.tagNames);

    const additional: Partial<Task> = {
      notes: payload.notes ?? '',
      ...(projectId ? { projectId } : {}),
      ...(tagIds.length ? { tagIds } : {}),
      ...(payload.timeEstimate ? { timeEstimate: payload.timeEstimate } : {}),
      // VERIFY(1): due-date field names in src/app/features/tasks/task.model.ts
      // current releases: dueDay / dueWithTime (+ hasPlannedTime); older: plannedAt
      ...(payload.dueDay ? { dueDay: payload.dueDay } : {}),
      ...(payload.dueWithTime
        ? { dueWithTime: payload.dueWithTime, hasPlannedTime: true }
        : {}),
    };

    // VERIFY(2): TaskService.add signature in task.service.ts — expected:
    //   add(title, isAddToBacklog = false, additional = {}, isAddToBottom = false)
    this._taskService.add(payload.title.trim(), false, additional);
  }

  private async _resolveProjectId(
    p: ExternalTaskPayload,
  ): Promise<string | undefined> {
    if (p.projectId) {
      return p.projectId;
    }
    if (!p.projectName) {
      return undefined;
    }
    const projects = await firstValueFrom(this._projectService.list$);
    return projects.find(
      (pr) => pr.title.toLowerCase() === p.projectName!.toLowerCase(),
    )?.id;
  }

  private async _resolveTagIds(names?: string[]): Promise<string[]> {
    if (!names?.length) {
      return [];
    }
    const tags = await firstValueFrom(this._tagService.tags$);
    return names
      .map((n) => tags.find((t) => t.title.toLowerCase() === n.toLowerCase())?.id)
      .filter((id): id is string => !!id);
  }
}
