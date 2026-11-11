# hooks

`hook-template.md` is a prompt for creating a hook, with the design choices to fill in and the checks to run. It links to the Claude Code hooks guide. Keep a hook script in `scripts/`, with no personal paths, a version and tests, as the three installed hooks are (`scripts/README.md`). `deploy.py hooks` registers those three; register any other hook in a settings file as the template describes.
