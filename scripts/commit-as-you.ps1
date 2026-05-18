# Commit staged changes using YOUR git config (ignores Cursor agent GIT_AUTHOR_* override).
# Usage: .\scripts\commit-as-you.ps1 -Message "feat: your message"
param(
    [Parameter(Mandatory = $true)][string]$Message
)
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
Remove-Item Env:GIT_AUTHOR_NAME -ErrorAction SilentlyContinue
Remove-Item Env:GIT_AUTHOR_EMAIL -ErrorAction SilentlyContinue
Remove-Item Env:GIT_COMMITTER_NAME -ErrorAction SilentlyContinue
Remove-Item Env:GIT_COMMITTER_EMAIL -ErrorAction SilentlyContinue
git commit -m $Message
git log -1 --format="author: %an <%ae>%ncommitter: %cn <%ce>"
