# Запуск всех тестов встроенным Python 3.7. Из корня репозитория:
#     .\tools\run_tests.ps1
#     .\tools\run_tests.ps1 -Pattern "test_roundtrip_*.py"     # только часть тестов
# Если запуск скриптов запрещён политикой (Restricted):
#     powershell -ExecutionPolicy Bypass -File tools\run_tests.ps1
# Последние строки вывода в PowerShell 5.1:
#     .\tools\run_tests.ps1 2>&1 | ForEach-Object { "$_" } | Select-Object -Last 4
#
# PATH: без Win64\python3.7\Library\bin встроенный Python не загружает DLL OCC
# (ImportError: DLL load failed). Каталог добавляется в начало PATH только на время
# запуска и убирается после (в том числе при ошибке). Код выхода — как у unittest.
param(
    [string]$Pattern = "test*.py"
)

# unittest пишет весь вывод в stderr: при 'Stop' у вызывающего скрипт оборвался бы на первой строке.
$ErrorActionPreference = "Continue"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "Win64\python3.7\python.exe"
$occBin = Join-Path $root "Win64\python3.7\Library\bin"

if (-not (Test-Path -LiteralPath $python)) {
    [Console]::Error.WriteLine("Не найден встроенный Python: $python")
    exit 2
}

$savedPath = $env:PATH
Push-Location -LiteralPath $root
try {
    $env:PATH = "$occBin;$savedPath"
    & $python -B -m unittest discover -s tests -p $Pattern -v
    $code = $LASTEXITCODE
}
finally {
    $env:PATH = $savedPath
    Pop-Location
}
exit $code
