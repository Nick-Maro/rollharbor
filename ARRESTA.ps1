[CmdletBinding()]
param([switch]$Json)
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
    if (-not $mutexOwned) { throw 'Un avvio del tavolo e ancora in corso.' }
    $stopped = @()
    foreach ($candidatePort in 8765..8775) {
        if (Test-DndPortAvailable $candidatePort) { continue }
        $health = Get-DndHealth $candidatePort
        if (Test-DndOwnServer $health $projectDirectory) {
            Stop-DndVerifiedServer $health $candidatePort $projectDirectory
            $stopped += $candidatePort
        }
    }
    if ($Json) { @{ ok = $true; stopped_ports = @($stopped) } | ConvertTo-Json -Compress }
    elseif ($stopped.Count -eq 0) { Write-Host 'Il tavolo e gia chiuso. Tutti i salvataggi sono conservati.' }
    else { Write-Host 'Tavolo chiuso. Tutti i salvataggi restano nella cartella.' -ForegroundColor Green }
} catch {
    $resultCode = 1
    if ($Json) { @{ ok = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress }
    else { Write-Host ('Server non arrestato: ' + $_.Exception.Message) }
} finally {
    if ($mutexOwned) { $taskMutex.ReleaseMutex() }
    if ($null -ne $taskMutex) { $taskMutex.Dispose() }
}
exit $resultCode
