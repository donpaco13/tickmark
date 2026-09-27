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
  This installer copies Tickmark and does not edit an agent's native task or
  status configuration.
#>

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

Write-Host ""
Write-Step "Next: use AGENTS.md only with a CLI that has no native progress view."
Write-Host "  See README.md for the integration rule and the CLI-specific location."
Write-Host ""
Write-Step 'Then check it works:  tk add "first step" ; tk'

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Warn "git was not found on PATH. tk looks for a project marker in parent directories; without one, lists can split across subfolders."
}

Write-Host ""
Write-Step "Done."
