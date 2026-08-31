[CmdletBinding()]
param([switch]$Online)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$expectedMerge = 'a616eea1350b095c6f229890d2c47e5010902330'
$reviewCommit = '5a55489fef8380f78854f10666a2fdd2983beeff'
$currentDocs = @(
    'docs/architecture/api-worker-boundary-follow-up-2026-08-18.md',
    'docs/architecture/database-design.md',
    'docs/architecture/implementation-progress.md',
    'docs/architecture/research-module-map.md',
    'docs/architecture/research-workflow-runtime.md',
    'docs/ssot/system-architecture.md',
    'specs/v5/post-v5-optimization/README.md',
    'specs/v5/post-v5-optimization/plan.md',
    'specs/v5/post-v5-optimization/research-boundary-runtime-design.md',
    'specs/v5/post-v5-optimization/spec.md',
    'specs/v5/post-v5-optimization/tasks.md'
)

Push-Location $repoRoot
try {
    git merge-base --is-ancestor $reviewCommit $expectedMerge
    if ($LASTEXITCODE -ne 0) { throw "R1 review $reviewCommit is not an ancestor of PR #22 merge $expectedMerge" }

    $originMain = (git rev-parse origin/main).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Unable to resolve origin/main' }
    git merge-base --is-ancestor $expectedMerge $originMain
    if ($LASTEXITCODE -ne 0) {
        throw "PR #22 merge $expectedMerge is not an ancestor of origin/main@$originMain"
    }

    $stalePatterns = @(
        'All R1 commits are local',
        'R1 commits remain local',
        'remote delivery remains pending',
        'remote push/PR/integration pending',
        'Push/integrate the accepted R1'
    )
    foreach ($file in $currentDocs) {
        $text = Get-Content -Raw -LiteralPath $file
        foreach ($pattern in $stalePatterns) {
            if ($text.Contains($pattern)) { throw "Stale R1 delivery claim '$pattern' in $file" }
        }
    }

    if ($Online) {
        $gh = (Get-Command gh -ErrorAction Stop).Source
        $pr = & $gh pr view 22 --repo Gujiassh/citeframe --json state,mergeCommit,statusCheckRollup | ConvertFrom-Json
        if ($pr.state -ne 'MERGED' -or $pr.mergeCommit.oid -ne $expectedMerge) {
            throw "PR #22 online truth mismatch: state=$($pr.state) merge=$($pr.mergeCommit.oid)"
        }
        $expectedChecks = @('api', 'worker-fast', 'worker-acceptance', 'worker-evaluation', 'web', 'web-e2e')
        $checks = @{}
        foreach ($check in $pr.statusCheckRollup) {
            if ($check.name) { $checks[$check.name] = $check.conclusion }
        }
        foreach ($name in $expectedChecks) {
            if (-not $checks.ContainsKey($name) -or $checks[$name] -ne 'SUCCESS') {
                throw "PR #22 check '$name' is not SUCCESS (actual=$($checks[$name]))"
            }
        }
        $unexpected = @($checks.Keys | Where-Object { $_ -notin $expectedChecks })
        if ($checks.Count -ne $expectedChecks.Count -or $unexpected.Count -ne 0) {
            throw "PR #22 check set differs from the frozen six: $($checks.Keys -join ', ')"
        }
        $remoteLine = git ls-remote origin refs/heads/main
        if ($LASTEXITCODE -ne 0 -or -not $remoteLine) { throw 'Unable to resolve remote main with git ls-remote' }
        $remoteMain = ($remoteLine -split '\s+')[0]
        if ($remoteMain -ne $originMain) {
            throw "Local origin/main@$originMain is stale relative to remote main@$remoteMain"
        }
        Write-Host "R1 online truth verified: PR #22 MERGED, six checks SUCCESS, remote main=$remoteMain"
    }

    Write-Host "R1 delivery truth verified: PR #22 merge=$expectedMerge origin/main=$originMain review=$reviewCommit"
}
finally {
    Pop-Location
}
