# Shared, local-only server identity checks for the Windows launchers.
function Get-DndHealth([int]$Port) {
    try { return Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 1 -ErrorAction Stop }
    catch { return $null }
}
function Test-DndOwnServer($Health, [string]$Directory) {
    if ($null -eq $Health -or $Health.ok -ne $true -or $Health.app -ne 'dnd-local-master') { return $false }
    try {
        $resolvedDirectory = [IO.Path]::GetFullPath([string]$Health.workspace).TrimEnd('\', '/')
        return [string]::Equals($resolvedDirectory, $Directory, [StringComparison]::OrdinalIgnoreCase)
    } catch { return $false }
}
function Test-DndPortAvailable([int]$Port) {
    $listener = $null
    try {
        $listener = New-Object System.Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $Port)
        $listener.Start(); return $true
    } catch { return $false }
    finally { if ($null -ne $listener) { $listener.Stop() } }
}
function Find-DndPython {
    foreach ($commandName in @('python', 'py')) {
        $command = Get-Command $commandName -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -eq $command) { continue }
        $pythonPrefix = @()
        if ($commandName -eq 'py') { $pythonPrefix = @('-3') }
        try {
            $result = & $command.Source @pythonPrefix -c "import sys; print('supported' if sys.version_info >= (3, 10) else 'outdated')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $result -eq 'supported') { return @{ Executable = $command.Source; Prefix = $pythonPrefix } }
        } catch { }
    }
    throw 'Serve Python 3.10 o successivo. Non occorrono pacchetti aggiuntivi per il tavolo.'
}
function Get-DndCodeFingerprint($Python, [string]$Directory) {
    $pythonArguments = @($Python.Prefix) + @((Join-Path $Directory 'runtime_info.py'), '--root', $Directory)
    $result = & $Python.Executable @pythonArguments
    if ($LASTEXITCODE -ne 0) { throw 'Non riesco a verificare la versione del server.' }
    $metadata = $result | ConvertFrom-Json
    if ([string]$metadata.fingerprint -notmatch '^[0-9a-f]{64}$') { throw 'Identificativo del codice non valido.' }
    return [string]$metadata.fingerprint
}
function Get-DndMutex([string]$Directory) {
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $hash = $hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($Directory.ToLowerInvariant())) }
    finally { $hasher.Dispose() }
    $key = ([BitConverter]::ToString($hash)).Replace('-', '').Substring(0, 24)
    return New-Object Threading.Mutex($false, "Local\DndTable-$key")
}
function Get-DndVerifiedProcess($Health, [int]$Port, [string]$Directory) {
    if (-not (Test-DndOwnServer $Health $Directory)) { throw 'Il servizio non appartiene a questa cartella.' }
    $serverPid = $Health.pid
    if ($null -eq $serverPid) {
        $infoFile = Join-Path $Directory 'logs\server.json'
        if (-not (Test-Path -LiteralPath $infoFile)) { throw 'Il vecchio server non ha un processo verificabile.' }
        $record = Get-Content -LiteralPath $infoFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $recordDirectory = [IO.Path]::GetFullPath([string]$record.workspace).TrimEnd('\', '/')
        if ($record.app -ne 'dnd-local-master' -or [int]$record.port -ne $Port -or -not [string]::Equals($recordDirectory, $Directory, [StringComparison]::OrdinalIgnoreCase)) { throw 'Il processo registrato non corrisponde al tavolo.' }
        $serverPid = $record.pid
    }
    $serverPid = [int]$serverPid
    if ($serverPid -le 0 -or $serverPid -eq $PID) { throw 'Identificativo del processo non valido.' }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $serverPid" -ErrorAction Stop
    $expectedServer = Join-Path $Directory 'server.py'
    $pathPattern = '(?i)(?:^|\s)"?' + [regex]::Escape($expectedServer) + '"?(?:\s|$)'
    $portPattern = '(?:^|\s)--port\s+"?' + [string]$Port + '"?(?:\s|$)'
    if ($null -eq $process -or ([string]$process.CommandLine -notmatch $pathPattern) -or ([string]$process.CommandLine -notmatch $portPattern)) { throw 'Il server e stato avviato manualmente o il processo non corrisponde. Riavvia quella sessione senza arrestare altri processi.' }
    return $process
}
function Stop-DndVerifiedServer($Health, [int]$Port, [string]$Directory) {
    $process = Get-DndVerifiedProcess $Health $Port $Directory
    $ownedProcess = Get-Process -Id ([int]$process.ProcessId) -ErrorAction Stop
    Stop-Process -Id $ownedProcess.Id -ErrorAction Stop
    if (-not $ownedProcess.WaitForExit(4000)) { throw 'Il server precedente non si e ancora chiuso.' }
}
