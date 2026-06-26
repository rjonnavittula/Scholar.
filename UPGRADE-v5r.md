# scholar. v5r — HIVE-Courses Forge replacement

Replaces the previous HIVE-Courses visual shell with the Scholar Forge / Neural Archives interaction model.

- Keeps Scholar's existing vanilla frontend contract: `window.HiveCourses.render(el, S, Api)`.
- Does not import React, Babel, Tailwind, Lottie, or CDN scripts into Scholar.
- Accepts pasted source text or complete system prompts.
- Parses modules deterministically instead of letting a model generate React nodes.
- Renders safe lesson blocks and diagrams without raw LLM HTML/JS.
