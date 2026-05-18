# Git commit attribution

GitHub shows **author** and **committer** separately. Commits made from Cursor Cloud often show
`committed by Cursor` even when the author is correct.

## Use your identity (recommended)

On your machine (Kali):

```bash
git config --global user.name "YOUR_GITHUB_USERNAME"
git config --global user.email "YOUR_GITHUB_EMAIL"
```

In Cursor: **Settings → General → Git** — set the same name and email.

CE auto-commits on `/end` use `git.user_name` / `git.user_email` from `~/.cognition/config.yaml`,
or `CE_GIT_USER_NAME` / `CE_GIT_USER_EMAIL` environment variables.

## Optional: rewrite old commits

Only if you own the repo and accept a force-push. See GitHub docs for `git filter-repo`.
