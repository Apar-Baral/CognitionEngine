# Git commit attribution

GitHub contributors are counted from **commit author email**. Historical commits used
`Dream Cognition Engine <cognition@local>`, so they may not appear under your account.

## Your commits going forward (Kali or any machine)

```bash
git config --global user.name "Apar-Baral"
git config --global user.email "dedsecaparb@gmail.com"
```

CE session auto-commits use the same identity from `~/.cognition/config.yaml` (`git.user_name` / `git.user_email`).

## Optional: rewrite old commits to your email

Only if you own the repo and accept a force-push to `master`:

```bash
git clone https://github.com/Apar-Baral/CognitionEngine.git
cd CognitionEngine
git filter-branch -f --env-filter '
export GIT_AUTHOR_NAME="Apar-Baral"
export GIT_AUTHOR_EMAIL="dedsecaparb@gmail.com"
export GIT_COMMITTER_NAME="Apar-Baral"
export GIT_COMMITTER_EMAIL="dedsecaparb@gmail.com"
' -- --all
git push --force-with-lease origin master
```

The repo `.mailmap` helps `git shortlog` and some tools show **Apar Baral** for old commits.
