# xss-finder (example)

Example scaffold for Cognition Engine **PHASE_01 Discovery**. Copy into your project:

```bash
cp -r examples/xss-finder/* ~/projects/xss-finder/
cd ~/projects/xss-finder
source ~/CognitionEngine/packages/cognition-engine/.venv/bin/activate
cognition-engine goal --set "$(cat GOAL.md | sed -n '3p')"
cognition-engine start
```

Then open `.cognition/bootstrap.md` in Cursor and implement from `docs/discovery.md`.
