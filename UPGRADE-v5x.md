# UPGRADE v5x — Course Progress Mutations

Adds the first saved progress loop for Scholar Courses.

## New API routes

- `POST /learn/nodes/{node_id}/start`
- `POST /learn/nodes/{node_id}/complete`

## Behavior

- Opening a lesson marks it `in_progress`.
- Completing a lesson marks the node complete.
- Node mastery is saved in Postgres.
- Module mastery is recalculated from its nodes.
- Completing a module unlocks the next module and node.
- Track status moves from `draft` to `active`, then `completed` when all modules are done.

## UI

The course lesson screen now has a real `Complete Lesson` mutation instead of only returning to the map.
