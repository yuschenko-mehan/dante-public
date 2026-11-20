# DANTE installer for Windows 10/11 / Встановлювач Данте для Windows 10/11
# Run Install-DANTE.cmd (it starts this file). / Запускайте Install-DANTE.cmd.
$ErrorActionPreference = "Continue"
$src = $PSScriptRoot
$dst = "C:\DANTE\dante"
function Has($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
Write-Host "=== DANTE: встановлення / installation ===" -ForegroundColor Cyan
if (-not (Has python) -or ((python --version 2>&1) -notmatch "Python 3\.(1[1-9]|[2-9]\d)")) {
  Write-Host "Встановлюю Python 3.13 / Installing Python 3.13 ..."
  winget install -e --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
  $env:Path = [Environment]::GetEnvironmentVariable("Path","User") + ";" + [Environment]::GetEnvironmentVariable("Path","Machine")
}
if (-not (Has python)) { Write-Host "Python не знайдено. Встановіть Python 3.13 з Microsoft Store і запустіть ще раз." -ForegroundColor Red; Read-Host "Enter"; exit 1 }
if (-not (Has git)) {
  Write-Host "Встановлюю Git / Installing Git ..."
  winget install -e --id Git.Git --accept-package-agreements --accept-source-agreements
}
if ((Resolve-Path $src).Path -ne $dst) {
  New-Item -ItemType Directory -Force -Path $dst | Out-Null
  # copy program files; never overwrite your keys, models, lessons or settings / ключі й налаштування не перезаписуються
  robocopy $src $dst /E /XF keys.txt models.json lessons.json dante.toml role.json /XD .git __pycache__ /NFL /NDL /NJH /NJS | Out-Null
  Write-Host "Файли скопійовано в $dst"
}
Set-Location $dst
python -m dante.install_wizard
