# Prepare the embedded Python runtime bundled into the SAB desktop installer.
#
# This assembles a fully offline runtime under desktop/runtime/ containing:
#   - a small CPython embeddable distribution (no metal, ~36MB unpacked)
#   - faster-whisper + deps (onnxruntime removed: not needed, VAD is disabled)
#   - the small Whisper 'base' model pre-seeded at runtime/models/whisper/
#
# Produced at build time and shipped via extraResources as resources/runtime/.
# desktop/runtime/ is gitignored — it is NOT committed to the repo.

param(
    [string]$PythonVersion = '3.14.0',
    [switch]$SkipModel
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$runtime = Join-Path $root 'runtime'
$wheelsDir = Join-Path (Split-Path $root -Parent) 'offline\wheels'

# ---------------------------------------------------------------------------
function Ensure-Download($Url, $Dest) {
    if (-not (Test-Path -LiteralPath $Dest)) {
        Write-Host "Downloading $Url"
        Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing
    }
}

# Clean any prior build so the runtime is deterministic
if (Test-Path -LiteralPath $runtime) {
    Write-Host 'Cleaning previous runtime...'
    Remove-Item -LiteralPath $runtime -Recurse -Force
}
New-Item -ItemType Directory -Path $runtime -Force | Out-Null

$zipName = "python-$PythonVersion-embed-amd64.zip"
$zipPath = Join-Path $runtime $zipName
$getPip = Join-Path $runtime 'get-pip.py'

Write-Host "== [1/5] Downloading embeddable CPython $PythonVersion =="
Ensure-Download "https://www.python.org/ftp/python/$PythonVersion/$zipName" $zipPath
Expand-Archive -LiteralPath $zipPath -DestinationPath $runtime -Force
Remove-Item -LiteralPath $zipPath -Force

$pyexe = Join-Path $runtime 'python.exe'
if (-not (Test-Path -LiteralPath $pyexe)) {
    throw 'python.exe not found after extracting embeddable distribution'
}

Write-Host '== [2/5] Configuring self-contained embeddable runtime =='
# The ._pth file is authoritative for the embeddable build. We ENABLE site so
# pip can install normally, and we make imports isolated via a sitecustomize.py
# (added in step 4b) that prunes sys.path down to runtime-internal dirs on every
# startup — guaranteeing the bundled python never reads the host machine's own
# Python site-packages, no matter who installs SAB.
$pthRel = Get-ChildItem -LiteralPath $runtime -Filter 'python*._pth' | Select-Object -First 1
if (-not $pthRel) { throw 'No ._pth file in embeddable distribution' }
$pthPath = $pthRel.FullName
$pthName = $pthRel.Name.Replace('._pth', '')
New-Item -ItemType Directory -Path (Join-Path $runtime 'Lib') -Force | Out-Null
$sitePkgs = Join-Path $runtime 'Lib\site-packages'
New-Item -ItemType Directory -Path $sitePkgs -Force | Out-Null
@(
    "$pthName.zip",
    '.',
    'Lib\site-packages',
    'import site'
) -join "`r`n" | Set-Content -LiteralPath $pthPath -Encoding ascii

Ensure-Download 'https://bootstrap.pypa.io/get-pip.py' $getPip
& $pyexe $getPip --no-warn-script-location | Out-Host

# IMPORTANT: install with --target into the runtime's OWN site-packages. This
# is the only way to guarantee packages land inside the runtime and never leak
# into the host machine's user/global site-packages.
Write-Host '== [3/5] Installing faster-whisper INTO runtime site-packages (offline) =='
if (Test-Path -LiteralPath $wheelsDir) {
    & $pyexe -m pip install --no-warn-script-location --no-index --find-links $wheelsDir --target $sitePkgs faster-whisper | Out-Host
} else {
    Write-Host '!! offline wheels not found; installing from PyPI instead'
    & $pyexe -m pip install --no-warn-script-location --target $sitePkgs faster-whisper | Out-Host
}

Write-Host '== [4/5] Removing onnxruntime (unused by ctranslate2, VAD disabled) =='
# onnxruntime is only a hard dependency (used solely by VAD, which we disable).
# Drop it to save ~76MB. Remove its dirs + dist-info from the runtime.
Get-ChildItem -LiteralPath $sitePkgs -Directory -Filter 'onnxruntime*' | Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $sitePkgs -File -Filter 'onnxruntime*' -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host '== [4b/5] Hardening isolation with sitecustomize =='
# sitecustomize.py runs during startup and keeps ONLY runtime-internal dirs on
# sys.path, so the bundled interpreter can never import host Python packages.
$runtimeAbs = (Resolve-Path -LiteralPath $runtime).Path
$sitecustomize = @'
import os, sys
_runtime = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_runtime_norm = os.path.normcase(os.path.realpath(_runtime))
_kept = []
for _p in sys.path:
    if not _p or _p == '.':
        _kept.append(_p)
        continue
    _abs = os.path.normcase(os.path.realpath(os.path.join(_runtime, _p) if not os.path.isabs(_p) else _p))
    if _abs.startswith(_runtime_norm):
        _kept.append(_p)
sys.path = _kept
'@
Set-Content -LiteralPath (Join-Path $sitePkgs 'sitecustomize.py') -Value $sitecustomize
Remove-Item Env:PYTHONUSERBASE -ErrorAction SilentlyContinue
Write-Host "Final $($pthRel.Name): $(Get-Content -LiteralPath $pthPath -Raw -ErrorAction SilentlyContinue | ForEach-Object { $_ -replace "`r?`n", ' | ' })"

Write-Host '== [5/5] Seeding Whisper model =='
if (-not $SkipModel) {
    $whisperSeed = Join-Path (Split-Path $root -Parent) 'offline\whisper-model\models--Systran--faster-whisper-base'
    $modelDest = Join-Path $runtime 'models\whisper\models--Systran--faster-whisper-base'
    if (Test-Path -LiteralPath $whisperSeed) {
        New-Item -ItemType Directory -Path (Split-Path $modelDest -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $whisperSeed -Destination $modelDest -Recurse -Force
        Write-Host "Seeded Whisper base model from $whisperSeed"
    } else {
        Write-Host '!! whisper-model seed not found under offline/whisper-model — first use will download it'
    }
}

Remove-Item -LiteralPath $getPip -Force -ErrorAction SilentlyContinue

$sizeMb = [math]::Round((Get-ChildItem -LiteralPath $runtime -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host "`nRUNTIME READY: $sizeMb MB at $runtime"
