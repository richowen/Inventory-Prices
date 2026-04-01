param(
    [string]$PiHost = "farmprices.west-stonecat.ts.net",
    [string]$PiUser = "richowen",
    [string]$Branch = "main",
    [string]$AppDir = "/home/richowen/farmprices",
    [string]$ServiceName = "farmprices",
    [switch]$SkipPush
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[deploy] $Message"
}

Write-Step "Starting deployment from Windows host"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git is not installed or not available in PATH."
}
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    throw "ssh is not installed or not available in PATH."
}

# Ensure this script is run from a git repository
$repoCheck = git rev-parse --is-inside-work-tree 2>$null
if ($LASTEXITCODE -ne 0 -or $repoCheck -ne "true") {
    throw "Run this script inside your local farmprices git repository."
}

$currentBranch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($currentBranch -ne $Branch) {
    throw "Current branch is '$currentBranch'. Checkout '$Branch' before deploying."
}

$status = git status --porcelain
if ($status) {
    throw "Working tree is not clean. Commit/stash changes before deploying."
}

if (-not $SkipPush) {
    Write-Step "Pushing local commits to origin/$Branch"
    git push origin $Branch
    if ($LASTEXITCODE -ne 0) {
        throw "git push failed."
    }
} else {
    Write-Step "SkipPush enabled; skipping git push"
}

$remoteCmd = @"
set -euo pipefail
APP_DIR='$AppDir' BRANCH='$Branch' SERVICE_NAME='$ServiceName' bash '$AppDir/deploy/remote_deploy.sh'
"@

Write-Step "Running remote deploy on $PiUser@$PiHost"
ssh "$PiUser@$PiHost" $remoteCmd
if ($LASTEXITCODE -ne 0) {
    throw "Remote deploy failed."
}

Write-Step "Deployment completed successfully"