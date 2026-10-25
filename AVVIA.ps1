[CmdletBinding()]
param([switch]$NoBrowser, [switch]$Json, [switch]$Restart)
$ErrorActionPreference = 'Stop'
$projectDirectory = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\', '/')
. (Join-Path $projectDirectory 'tools\windows-runtime.ps1')
$taskMutex = $null
$mutexOwned = $false
$resultCode = 0
try {
    $taskMutex = Get-DndMutex $projectDirectory
    try { $mutexOwned = $taskMutex.WaitOne(10000) }
    catch [Threading.AbandonedMutexException] { $mutexOwned = $true }
    if (-not $mutexOwned) { throw 'Un altro avvio e ancora in corso. Attendi qualche secondo e riprova.' }
    $serverFile = Join-Path $projectDirectory 'server.py'
    if (-not (Test-Path -LiteralPath $serverFile -PathType Leaf)) { throw 'Non trovo server.py nella cartella.' }
    $pythonChoice = Find-DndPython
    $fingerprint = Get-DndCodeFingerprint $pythonChoice $projectDirectory
    $selectedPort = $null
    $availablePort = $null
    $runningHealth = $null
    foreach ($candidatePort in 8765..8775) {
        if (Test-DndPortAvailable $candidatePort) {
            if ($null -eq $availablePort) { $availablePort = $candidatePort }
        } else {
            $candidateHealth = Get-DndHealth $candidatePort
            if (Test-DndOwnServer $candidateHealth $projectDirectory) {
                $selectedPort = $candidatePort
                $runningHealth = $candidateHealth
                break
            }
        }
    }
    $restarted = $false
    $reused = $false
    if ($null -ne $runningHealth) {
        if ($Restart -or [string]$runningHealth.runtime_fingerprint -ne $fingerprint) {
            if (-not $Json) { Write-Host 'Aggiorno il server del tavolo; i salvataggi restano conservati...' -ForegroundColor DarkYellow }
            Stop-DndVerifiedServer $runningHealth $selectedPort $projectDirectory
            $runningHealth = $null
            $restarted = $true
        } else { $reused = $true }
    }
    if ($null -eq $selectedPort) { $selectedPort = $availablePort }
    if ($null -eq $selectedPort) { throw 'Le porte locali da 8765 a 8775 sono occupate.' }
    if ($null -eq $runningHealth) {
        $logDirectory = Join-Path $projectDirectory 'logs'
        New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
        $outputLog = Join-Path $logDirectory "server-$selectedPort.log"
        $errorLog = Join-Path $logDirectory "server-$selectedPort.error.log"
        if (-not $Json) { Write-Host 'Preparo il tavolo di gioco...' -ForegroundColor DarkYellow }
        $launchArguments = @($pythonChoice.Prefix) + @((Join-Path $projectDirectory 'runtime_info.py'), '--root', $projectDirectory, '--launch-server', '--port', [string]$selectedPort)
        $launchOutput = & $pythonChoice.Executable @launchArguments
        if ($LASTEXITCODE -ne 0) { throw 'Avvio del processo del tavolo non riuscito.' }
        $launchInfo = $launchOutput | ConvertFrom-Json
        $launchedPid = [int]$launchInfo.pid
        $deadline = [DateTime]::UtcNow.AddSeconds(8)
        do {
            $runningHealth = Get-DndHealth $selectedPort
            if ((Test-DndOwnServer $runningHealth $projectDirectory) -and [string]$runningHealth.runtime_fingerprint -eq $fingerprint) { break }
            if ($null -eq (Get-Process -Id $launchedPid -ErrorAction SilentlyContinue)) { break }
            Start-Sleep -Milliseconds 150
        } while ([DateTime]::UtcNow -lt $deadline)
        if (-not (Test-DndOwnServer $runningHealth $projectDirectory) -or [string]$runningHealth.runtime_fingerprint -ne $fingerprint) { throw "Il server aggiornato non e partito. Controlla $errorLog" }
        $serverRecord = @{
            pid = $launchedPid; port = $selectedPort; app = 'dnd-local-master'
            workspace = $projectDirectory; executable = $pythonChoice.Executable
            runtime_fingerprint = $fingerprint; started_at = [DateTime]::UtcNow.ToString('o')
        }
        $recordFile = Join-Path $logDirectory 'server.json'
        $temporaryRecord = Join-Path $logDirectory ('server-' + [guid]::NewGuid().ToString('N') + '.tmp')
        $serverRecord | ConvertTo-Json | Set-Content -LiteralPath $temporaryRecord -Encoding UTF8
        Move-Item -LiteralPath $temporaryRecord -Destination $recordFile -Force
    }
    $gameUrl = "http://127.0.0.1:$selectedPort/"
    $gameTable = Invoke-RestMethod -Uri ($gameUrl + 'api/table') -TimeoutSec 3
    $gameState = $gameTable.state
    $gameStatus = $gameTable.status
    $output = @{
        ok = $true; url = $gameUrl; port = $selectedPort; pid = $runningHealth.pid
        reused = $reused; restarted = $restarted; campaign_id = $gameState.campaign_id
        party_count = @($gameState.party).Count; party_size = $gameState.party_size
        ready = $gameStatus.group_ready
        started = $gameStatus.started; revision = $gameState.revision
        browser_opened = $false
    }
    if (-not $NoBrowser) {
        try { Start-Process $gameUrl | Out-Null; $output.browser_opened = $true }
        catch { $output.browser_error = $_.Exception.Message }
    }
    if ($Json) { $output | ConvertTo-Json -Compress }
    else {
        Write-Host "Il tavolo e pronto: $gameUrl" -ForegroundColor Green
        if ($output.ContainsKey('browser_error')) { Write-Host "Apri questo indirizzo nel browser: $gameUrl" }
        Write-Host 'Parla con il master nella chat: puoi dire Avvia la partita o descrivere un personaggio.'
    }
} catch {
    $resultCode = 1
    if ($Json) { @{ ok = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress }
    else {
        Write-Host ('Impossibile aprire il tavolo: ' + $_.Exception.Message) -ForegroundColor Red
        if (-not $NoBrowser -and $Host.Name -eq 'ConsoleHost') { Write-Host 'Premi INVIO per chiudere.'; [void](Read-Host) }
    }
} finally {
    if ($mutexOwned) { $taskMutex.ReleaseMutex() }
    if ($null -ne $taskMutex) { $taskMutex.Dispose() }
}
exit $resultCode
