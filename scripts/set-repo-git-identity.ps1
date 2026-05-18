# Set git author for THIS repo only (run from repo root on Windows).
# Usage: .\scripts\set-repo-git-identity.ps1 -Name "YourName" -Email "you@example.com"
param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$Email
)
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
git config user.name $Name
git config user.email $Email
Write-Host "Repo git identity set:"
git config user.name
git config user.email
