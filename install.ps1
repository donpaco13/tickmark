#Requires -Version 5.1
<#
tickmark installer for Windows / PowerShell -- copies `tk` onto your PATH,
generates a `tk.cmd` wrapper (Windows can't run a Python shebang script
directly), and shows each agent where to read its instructions. Mirrors
install.sh: same install directory convention, same "always overwrite" so a
`git pull` is never left running a stale `tk`, same non-destructive stance
toward files it doesn't own.

Usage
-----
  git clone https://github.com/donpaco13/tickmark
  cd tickmark
  .\install.ps1

If PowerShell refuses to run this script ("running scripts is disabled on
this system"), that is Windows' default execution policy, not a bug here.
Run it once with:
  powershell -ExecutionPolicy Bypass -File install.ps1

Flags
-----
  -SkipStatusLine   Don't touch Claude Code's settings.json even if found.
#>
[CmdletBinding()]
param(
    [switch]$SkipStatusLine
)

$ErrorActionPreference = 'Stop'

function Write-Step  { param([string]$Msg) Write-Host $Msg }
function Write-Warn  { param([string]$Msg) Write-Host "  ! $Msg" -ForegroundColor Yellow }
function Write-Found { param([string]$Msg) Write-Host "  found  $Msg" }
function Write-Miss  { param([string]$Msg) Write-Host "  ! could not $Msg" -ForegroundColor Yellow }

$SrcDir = $PSScriptRoot

# ---------------------------------------------------------------------------
# 1. Require a real Python 3 interpreter. Windows ships a `python` /
#    `python3` App Execution Alias that silently no-ops (or pops the Store)
#    when no interpreter is installed -- filter that out rather than trust
#    Get-Command alone.
# ---------------------------------------------------------------------------
function Test-IsStoreAlias {
    param([string]$Path)
    if ($Path -notmatch 'WindowsApps') { return $false }
    try { return (Get-Item -LiteralPath $Path).Length -lt 100000 }
    catch { return $true }
}

function Get-PythonCommand {
    $candidates = @(
        [pscustomobject]@{ Cmd = 'py';       Args = @('-3') },
        [pscustomobject]@{ Cmd = 'python3';  Args = @() },
        [pscustomobject]@{ Cmd = 'python';   Args = @() }
    )
    foreach ($c in $candidates) {
        $info = Get-Command $c.Cmd -ErrorAction SilentlyContinue
        if (-not $info) { continue }
        if (Test-IsStoreAlias $info.Source) { continue }
        $verArgs = $c.Args + '--version'
        try { $out = & $c.Cmd @verArgs 2>&1 } catch { continue }
        if ($LASTEXITCODE -eq 0 -and ($out -join ' ') -match 'Python 3\.') {
            return $c
        }
    }
    return $null
}

$Python = Get-PythonCommand
if (-not $Python) {
    Write-Host "tickmark needs a Python 3 interpreter on your PATH (python.org, or 'winget install Python.Python.3')." -ForegroundColor Red
    exit 1
}
$PythonLabel = if ($Python.Args) { "$($Python.Cmd) $($Python.Args -join ' ')" } else { $Python.Cmd }
Write-Step "Using $PythonLabel"

# ---------------------------------------------------------------------------
# 2. Install `tk` + a `tk.cmd` wrapper. Always overwrite: a stale copy from
#    before the last `git pull` is worse than a slower install, and this
#    keeps behavior identical to install.sh's unconditional `cp`.
# ---------------------------------------------------------------------------
$Bin = if ($env:TICKMARK_BIN) { $env:TICKMARK_BIN } else { Join-Path $HOME '.local\bin' }
New-Item -ItemType Directory -Force -Path $Bin | Out-Null

Copy-Item -LiteralPath (Join-Path $SrcDir 'tk') -Destination (Join-Path $Bin 'tk') -Force

$WrapperArgs = ($Python.Args -join ' ')
$WrapperCmd  = if ($WrapperArgs) { "$($Python.Cmd) $WrapperArgs" } else { $Python.Cmd }
$WrapperBody = "@echo off`r`n$WrapperCmd `"%~dp0tk`" %*`r`n"
[System.IO.File]::WriteAllText((Join-Path $Bin 'tk.cmd'), $WrapperBody, [System.Text.ASCIIEncoding]::new())

Write-Step "Installed $Bin\tk (+ tk.cmd wrapper)"

# ---------------------------------------------------------------------------
# 3. Put $Bin on the user's PATH -- idempotent: skip if a case-insensitive,
#    trailing-slash-insensitive match is already there. User scope only, no
#    admin needed, mirrors install.sh never touching a system-wide PATH.
# ---------------------------------------------------------------------------
function Add-UserPathEntry {
    param([string]$Dir)
    $current = [Environment]::GetEnvironmentVariable('Path', 'User')
    $parts = @()
    if ($current) { $parts = $current -split ';' | Where-Object { $_ -ne '' } }
    $normalized = $Dir.TrimEnd('\')
    $already = $parts | Where-Object { $_.TrimEnd('\') -ieq $normalized }
    if ($already) { return $false }
    $newPath = if ($current) { "$current;$Dir" } else { $Dir }
    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
    return $true
}

if (Add-UserPathEntry -Dir $Bin) {
    Write-Step "Added $Bin to your user PATH (open a new terminal for it to apply everywhere)."
    # Make it usable in *this* terminal immediately too.
    if (($env:Path -split ';') -notcontains $Bin) { $env:Path = "$env:Path;$Bin" }
} else {
    Write-Step "$Bin is already on your user PATH."
}

# ---------------------------------------------------------------------------
# 4. Detect agent instruction files (same global paths install.sh checks,
#    Windows separators). Many CLIs -- Antigravity CLI (agy) included -- only
#    read a project-local AGENTS.md instead; flag those separately rather
#    than guess an unverified per-CLI folder layout.
# ---------------------------------------------------------------------------
Write-Host ""
Write-Step "Next: paste AGENTS.md into the instruction file your agent reads."
Write-Host ""

$GlobalInstructionFiles = @(
    (Join-Path $HOME '.claude\CLAUDE.md'),
    (Join-Path $HOME '.codex\AGENTS.md'),
    (Join-Path $HOME '.config\opencode\AGENTS.md'),
    (Join-Path $HOME '.gemini\GEMINI.md'),
    (Join-Path $HOME '.config\crush\CRUSH.md'),
    (Join-Path $HOME '.aider.conf.yml')
)

$foundGlobal = $false
foreach ($f in $GlobalInstructionFiles) {
    if (Test-Path -LiteralPath $f) {
        Write-Found $f
        $foundGlobal = $true
    }
}

$ProjectOnlyCli = @('agy')  # binaries whose instruction file is project-local, not global
$foundProjectOnly = @()
foreach ($cmd in $ProjectOnlyCli) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        $foundProjectOnly += $cmd
    }
}
foreach ($cmd in $foundProjectOnly) {
    Write-Found "$cmd on PATH -- it reads a project-local AGENTS.md, not a file under `$HOME (see README's table)"
}

if (-not $foundGlobal -and $foundProjectOnly.Count -eq 0) {
    Write-Host "  (no known agent instruction file found -- see the README)"
}

Write-Host ""
Write-Host "  Get-Content `"$SrcDir\AGENTS.md`" | Add-Content <that file>"
Write-Host ""
Write-Step 'Then check it works:  tk add "first step" ; tk'

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Warn "git was not found on PATH. tk falls back to the current directory for its project root instead of the git root, so its list can split across subfolders of the same repo."
}

# ---------------------------------------------------------------------------
# 5. Claude Code statusLine -- the one integration in integrations/ with a
#    documented, stable JSON contract, so it's the only one wired
#    automatically. Never touched if -SkipStatusLine, if Claude Code isn't
#    present, or if settings.json already points somewhere else (never
#    clobber a user's existing customization).
# ---------------------------------------------------------------------------
$ClaudeDir = Join-Path $HOME '.claude'
if (-not $SkipStatusLine -and (Test-Path -LiteralPath $ClaudeDir)) {
    Write-Host ""
    Write-Step "Claude Code detected -- wiring its status line to tk."

    $StatusEngineSrc = Join-Path $SrcDir 'integrations\tk-status.py'
    if (-not (Test-Path -LiteralPath $StatusEngineSrc)) {
        Write-Miss "find integrations\tk-status.py next to this script -- skipping the status line."
    } else {
        $StatusEngineDst = Join-Path $Bin 'tk-status.py'
        Copy-Item -LiteralPath $StatusEngineSrc -Destination $StatusEngineDst -Force

        $Command = "$($Python.Cmd)$(if ($WrapperArgs) { " $WrapperArgs" }) `"$StatusEngineDst`" --stdin-json"
        $SettingsPath = Join-Path $ClaudeDir 'settings.json'

        $Settings = $null
        $ParseFailed = $false
        if (Test-Path -LiteralPath $SettingsPath) {
            $raw = Get-Content -LiteralPath $SettingsPath -Raw
            if ($raw.Trim()) {
                try { $Settings = $raw | ConvertFrom-Json } catch { $ParseFailed = $true }
            } else {
                $Settings = [pscustomobject]@{}
            }
        } else {
            $Settings = [pscustomobject]@{}
        }

        if ($ParseFailed) {
            Write-Miss "parse $SettingsPath (invalid JSON) -- left it untouched. Add this by hand:"
            Write-Host "    `"statusLine`": { `"type`": `"command`", `"command`": `"$Command`" }"
        } else {
            $already = $Settings.PSObject.Properties['statusLine'] -and
                       $Settings.statusLine.PSObject.Properties['command'] -and
                       $Settings.statusLine.command -eq $Command
            $ownedByOther = $Settings.PSObject.Properties['statusLine'] -and -not $already

            if ($already) {
                Write-Step "  $SettingsPath already points at tk-status.py -- nothing to change."
            } elseif ($ownedByOther) {
                Write-Warn "$SettingsPath already has a different statusLine -- left it as-is. To use tk instead, set:"
                Write-Host "    `"statusLine`": { `"type`": `"command`", `"command`": `"$Command`" }"
            } else {
                $BackupPath = "${SettingsPath}.bak"
                if ((Test-Path -LiteralPath $SettingsPath -PathType Leaf) -and -not (Test-Path -LiteralPath $BackupPath)) {
                    Copy-Item -LiteralPath $SettingsPath -Destination $BackupPath
                }
                $Settings | Add-Member -NotePropertyName statusLine -NotePropertyValue ([pscustomobject]@{
                    type    = 'command'
                    command = $Command
                }) -Force
                $json = $Settings | ConvertTo-Json -Depth 20
                [System.IO.File]::WriteAllText($SettingsPath, $json, [System.Text.UTF8Encoding]::new($false))
                Write-Step "  Wired $SettingsPath -> tk-status.py (backup at $BackupPath if one didn't already exist)"
            }
        }
    }
}

Write-Host ""
Write-Step "Done."
