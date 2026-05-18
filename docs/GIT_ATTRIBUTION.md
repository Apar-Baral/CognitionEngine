# Git commit attribution

If commits show **Dream Cognition Engine** or **Cursor** instead of your name, that comes from
the **git identity on the machine that ran `git commit`** — not from the CE Python package.

## Fix on Kali (your commits going forward)

```bash
git config --global user.name "YOUR_GITHUB_USERNAME"
git config --global user.email "YOUR_GITHUB_EMAIL"
git config --global --list | grep user
```

Use the **same email** linked to your GitHub account (Settings → Emails).

## Fix in Cursor (when the agent pushes from the IDE)

**Settings → General → Git** — set your name and email there too.

## CE session commits (`/end` auto-commit)

In `~/.cognition/config.yaml`:

```yaml
git:
  user_name: YOUR_GITHUB_USERNAME
  user_email: YOUR_GITHUB_EMAIL
```

Or export before running CE:

```bash
export CE_GIT_USER_NAME="YOUR_GITHUB_USERNAME"
export CE_GIT_USER_EMAIL="YOUR_GITHUB_EMAIL"
```

## Old commits already on GitHub

Those keep the old author until you rewrite history (optional, force-push required).
New commits after fixing `git config` will show your name.
