$ErrorActionPreference = 'Stop'
$paperRoot = Split-Path -Parent $PSScriptRoot
$paperCompiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $paperCompiler)) { throw 'The Windows .NET Framework C# compiler is unavailable.' }
$paperSource = Join-Path $paperRoot 'launcher_src\PaperRouteLauncher.cs'
$paperIcon = Join-Path $paperRoot 'assets\paperroute.ico'
$paperOutput = Join-Path $paperRoot 'PaperRoute.exe'
& $paperCompiler /nologo /target:winexe /platform:x64 /optimize+ /reference:System.Windows.Forms.dll "/win32icon:$paperIcon" "/out:$paperOutput" $paperSource
if ($LASTEXITCODE -ne 0) { throw 'PaperRoute launcher compilation failed.' }
Copy-Item -LiteralPath $paperOutput -Destination (Join-Path $paperRoot 'pdf2zh.exe') -Force
Get-Item -LiteralPath $paperOutput | Select-Object Name, Length, LastWriteTime
