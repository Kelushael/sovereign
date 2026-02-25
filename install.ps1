# ═══════════════════════════════════════════════════════════════════════════════
#  sovereign — PowerShell installer
#  Windows 10/11 · Windows Server · PowerShell Core (Linux/macOS)
#
#  iwr -useb https://markyninox.com/install.ps1 | iex
# ═══════════════════════════════════════════════════════════════════════════════
$ErrorActionPreference = 'Stop'

$REPO   = "https://raw.githubusercontent.com/Kelushael/sovereign/main"
$BIN    = "$HOME\.local\bin"
$DEST   = "$BIN\sovereign.py"
$CHERUB = "$BIN\cherub.py"

# Cross-platform bin path
if ($IsLinux -or $IsMacOS) {
    $BIN    = "$HOME/.local/bin"
    $DEST   = "$BIN/sovereign.py"
    $CHERUB = "$BIN/cherub.py"
}

function Write-Lime   { param($m) Write-Host "  $m" -ForegroundColor Green }
function Write-Cyan   { param($m) Write-Host "  $m" -ForegroundColor Cyan  }
function Write-Pink   { param($m) Write-Host "  $m" -ForegroundColor Magenta }
function Write-Dim    { param($m) Write-Host "  $m" -ForegroundColor DarkGray }
function Write-Err    { param($m) Write-Host "  $m" -ForegroundColor Red }

Write-Host ""
Write-Pink  "sovereign installer"
Write-Dim   "zero-config · zero local compute · your stack"
Write-Host ""

# ── OS DETECTION ──────────────────────────────────────────────────────────────
$IsWin = $PSVersionTable.Platform -eq 'Win32NT' -or $env:OS -eq 'Windows_NT' -or (-not ($IsLinux -or $IsMacOS))
Write-Dim "platform: $($PSVersionTable.Platform ?? 'Windows') · PS $($PSVersionTable.PSVersion)"

# ── PYTHON ────────────────────────────────────────────────────────────────────
$python = $null
foreach ($cmd in @('python3','python','py')) {
    try {
        $v = & $cmd -c "import sys; print(sys.version_info.major)" 2>$null
        if ($v -ge 3) { $python = $cmd; break }
    } catch {}
}

if (-not $python) {
    Write-Dim "python3 not found — installing..."

    if ($IsWin) {
        # Try winget first
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Write-Dim "using winget..."
            winget install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
        }
        # Try chocolatey
        elseif (Get-Command choco -ErrorAction SilentlyContinue) {
            Write-Dim "using chocolatey..."
            choco install python3 -y --no-progress
        }
        # Try scoop
        elseif (Get-Command scoop -ErrorAction SilentlyContinue) {
            Write-Dim "using scoop..."
            scoop install python
        }
        else {
            Write-Host ""
            Write-Err  "no package manager found. install Python 3 from:"
            Write-Cyan "https://www.python.org/downloads/"
            Write-Dim  "then re-run this script."
            exit 1
        }
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
    }
    elseif ($IsLinux) {
        if (Get-Command apt-get  -EA 0) { sudo apt-get install -y -qq python3 python3-pip }
        elseif (Get-Command dnf  -EA 0) { sudo dnf install -y python3 python3-pip }
        elseif (Get-Command pacman -EA 0) { sudo pacman -Sy --noconfirm python python-pip }
        elseif (Get-Command apk  -EA 0) { sudo apk add --quiet python3 py3-pip }
        else { Write-Err "install python3 manually then re-run"; exit 1 }
    }
    elseif ($IsMacOS) {
        if (Get-Command brew -EA 0) { brew install python3 }
        else {
            Write-Err "install Homebrew first: https://brew.sh"; exit 1
        }
    }

    foreach ($cmd in @('python3','python','py')) {
        try { $v = & $cmd -c "import sys; print(sys.version_info.major)" 2>$null
              if ($v -ge 3) { $python = $cmd; break } } catch {}
    }
}

if (-not $python) { Write-Err "python3 install failed — install manually"; exit 1 }
Write-Lime "python  →  $(Get-Command $python | Select-Object -ExpandProperty Source)"

# ── PIP + REQUESTS ────────────────────────────────────────────────────────────
try { & $python -m pip --version 2>$null | Out-Null } catch {
    Write-Dim "pip not found — installing..."
    if ($IsWin -and (Get-Command py -EA 0)) { py -m ensurepip }
    else { & $python -m ensurepip --upgrade 2>$null }
}

try { & $python -c "import requests" 2>$null } catch {
    Write-Dim "installing requests..."
    & $python -m pip install --quiet --user requests 2>$null
    if ($LASTEXITCODE -ne 0) { & $python -m pip install --quiet requests }
}
Write-Lime "requests"

# ── DOWNLOAD ──────────────────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $BIN | Out-Null

Write-Dim "downloading sovereign..."
$wc = New-Object System.Net.WebClient
$wc.Headers.Add("User-Agent", "sovereign-installer/1.0")
$wc.DownloadFile("$REPO/sovereign.py", $DEST)
$wc.DownloadFile("$REPO/cherub.py",    $CHERUB)
Write-Lime "sovereign  →  $DEST"
Write-Lime "cherub     →  $CHERUB"

# ── WRAPPERS (sovereign / cherub commands) ────────────────────────────────────
if ($IsWin) {
    # Create .cmd wrappers so 'sovereign' works in cmd.exe and PowerShell
    $sovCmd = "$BIN\sovereign.cmd"
    $chbCmd = "$BIN\cherub.cmd"
    "@echo off`r`n$python `"$DEST`" %*" | Set-Content $sovCmd -Encoding ASCII
    "@echo off`r`n$python `"$CHERUB`" %*" | Set-Content $chbCmd -Encoding ASCII
    Write-Lime "wrappers   →  sovereign.cmd / cherub.cmd"

    # Add BIN to user PATH if needed
    $userPath = [System.Environment]::GetEnvironmentVariable("Path","User") ?? ""
    if ($userPath -notlike "*$BIN*") {
        [System.Environment]::SetEnvironmentVariable("Path", "$BIN;$userPath", "User")
        $env:Path = "$BIN;$env:Path"
        Write-Lime "PATH       →  $BIN added"
    }
} else {
    # Create sh wrapper
    $sovSh = "$BIN/sovereign"
    $chbSh = "$BIN/cherub"
    "#!/bin/sh`n$python `"$DEST`" `"`$@`"" | Set-Content $sovSh
    "#!/bin/sh`n$python `"$CHERUB`" `"`$@`"" | Set-Content $chbSh
    chmod +x $sovSh $chbSh 2>$null
    Write-Lime "wrappers   →  sovereign / cherub"

    # Add to PATH in shell rc files
    foreach ($rc in @("$HOME/.bashrc","$HOME/.zshrc","$HOME/.profile")) {
        if ((Test-Path $rc) -and -not (Select-String -Path $rc -Pattern ".local/bin" -Quiet)) {
            Add-Content $rc "`nexport PATH=`"`$HOME/.local/bin:`$PATH`""
        }
    }
    $env:PATH = "$BIN:$env:PATH"
    Write-Lime "PATH"
}

# ── TOKEN ─────────────────────────────────────────────────────────────────────
$tokenFile = if ($IsWin) { "$HOME\.axis-token" } else { "$HOME/.axis-token" }

if (Test-Path $tokenFile) {
    Write-Lime "token      →  found at $tokenFile"
} elseif ($env:AXIS_TOKEN) {
    $env:AXIS_TOKEN | Set-Content $tokenFile
    Write-Lime "token      →  saved from env"
} else {
    Write-Host ""
    Write-Dim  "no token yet. set it with:"
    if ($IsWin) {
        Write-Cyan '  $env:AXIS_TOKEN="your-token"; iwr -useb https://markyninox.com/install.ps1 | iex'
    } else {
        Write-Cyan '  $env:AXIS_TOKEN="your-token"; iwr -useb https://markyninox.com/install.ps1 | iex'
    }
    Write-Dim  "or manually:  'your-token' | Set-Content `"$tokenFile`""
}

# ── DONE ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Pink  "sovereign is ready."
Write-Host ""
if ($IsWin) {
    Write-Dim  "open a new terminal, then:"
} else {
    Write-Dim  "reload your shell, then:"
}
Write-Lime "sovereign"
Write-Dim  "cherub"
Write-Host ""
