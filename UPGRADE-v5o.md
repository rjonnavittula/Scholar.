# Upgrade v5o — HIVE-Courses Shell

This patch adds the first HIVE-Courses surface inside Scholar.

## Adds

- New rail button: `HIVE-Courses` (`✦`)
- New view container: `#learn`
- `webui/js/learn.js`
- Brilliant-style lesson canvas shell
- Boot.dev-style course roadmap shell
- Course/task-derived stats from existing Scholar state

## Does not add yet

- Database tables for learning progress
- Ollama/local AI generation
- Exercise attempts
- Lesson persistence

Those belong in the next patches so the first patch stays low-risk and easy to review.

## Test

```bash
python -m compileall app
node --check webui/js/api.js
node --check webui/js/calendar.js
node --check webui/js/panel.js
node --check webui/js/learn.js
node --check webui/js/app.js
```

Then run Scholar and click the `✦` rail button.
