$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendDirectory = Join-Path $projectRoot 'backend'
$frontendDirectory = Join-Path $projectRoot 'frontend'
$pythonPath = Join-Path $backendDirectory 'venv\Scripts\python.exe'
$managePath = Join-Path $backendDirectory 'manage.py'
$nodeModulesPath = Join-Path $frontendDirectory 'node_modules'

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    [Console]::Error.WriteLine("ERROR: Backend Python was not found: $pythonPath")
    exit 1
}

if (-not (Test-Path -LiteralPath $managePath -PathType Leaf)) {
    [Console]::Error.WriteLine("ERROR: Django manage.py was not found: $managePath")
    exit 1
}

if (-not (Test-Path -LiteralPath $nodeModulesPath -PathType Container)) {
    [Console]::Error.WriteLine("ERROR: Frontend dependencies were not found: $nodeModulesPath")
    [Console]::Error.WriteLine("Run npm.cmd install in the frontend directory, then try again.")
    exit 1
}

$npmCommand = Get-Command 'npm.cmd' -ErrorAction SilentlyContinue
if (-not $npmCommand) {
    [Console]::Error.WriteLine('ERROR: npm.cmd was not found on PATH.')
    exit 1
}

function Stop-ProcessTree {
    param(
        [System.Diagnostics.Process]$RootProcess,
        [string]$ServiceName
    )

    if ($null -eq $RootProcess) {
        return
    }

    try {
        $processes = @(Get-CimInstance -ClassName Win32_Process -ErrorAction Stop)
        $processIds = New-Object 'System.Collections.Generic.List[int]'
        $pendingIds = New-Object 'System.Collections.Generic.Queue[int]'
        $processIds.Add($RootProcess.Id)
        $pendingIds.Enqueue($RootProcess.Id)

        while ($pendingIds.Count -gt 0) {
            $parentId = $pendingIds.Dequeue()
            foreach ($process in $processes) {
                if ([int]$process.ParentProcessId -eq $parentId) {
                    $childId = [int]$process.ProcessId
                    if (-not $processIds.Contains($childId)) {
                        $processIds.Add($childId)
                        $pendingIds.Enqueue($childId)
                    }
                }
            }
        }

        $idsToStop = $processIds.ToArray()
        [array]::Reverse($idsToStop)
        foreach ($processId in $idsToStop) {
            if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
                try {
                    Stop-Process -Id $processId -Force -ErrorAction Stop
                }
                catch {
                    [Console]::Error.WriteLine(
                        "WARNING: Could not stop $ServiceName process $processId`: $($_.Exception.Message)"
                    )
                }
            }
        }
    }
    catch {
        [Console]::Error.WriteLine(
            "WARNING: Could not inspect the $ServiceName process tree: $($_.Exception.Message)"
        )
        if (Get-Process -Id $RootProcess.Id -ErrorAction SilentlyContinue) {
            try {
                Stop-Process -Id $RootProcess.Id -Force -ErrorAction Stop
            }
            catch {
                [Console]::Error.WriteLine(
                    "WARNING: Could not stop $ServiceName process $($RootProcess.Id): $($_.Exception.Message)"
                )
            }
        }
    }
}

$backendProcess = $null
$frontendProcess = $null
$backendArguments = '"{0}" runserver 127.0.0.1:8000 --noreload' -f $managePath
$frontendArguments = '/d /s /c ""{0}" run dev"' -f $npmCommand.Source

try {
    $backendProcess = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList $backendArguments `
        -WorkingDirectory $backendDirectory `
        -PassThru `
        -NoNewWindow `
        -ErrorAction Stop

    $frontendProcess = Start-Process `
        -FilePath $env:ComSpec `
        -ArgumentList $frontendArguments `
        -WorkingDirectory $frontendDirectory `
        -PassThru `
        -NoNewWindow `
        -ErrorAction Stop
}
catch {
    [Console]::Error.WriteLine("ERROR: Could not start both services: $($_.Exception.Message)")
    Stop-ProcessTree -RootProcess $frontendProcess -ServiceName 'Frontend'
    Stop-ProcessTree -RootProcess $backendProcess -ServiceName 'Backend'
    exit 1
}

Write-Host 'Backend:  http://127.0.0.1:8000'
Write-Host 'Frontend: http://127.0.0.1:5173'
Write-Host 'Both services are running as separate processes. Press Ctrl+C to stop them.'

$exitCode = 0
try {
    while ($true) {
        foreach ($service in @(
            [PSCustomObject]@{ Name = 'Backend'; Process = $backendProcess },
            [PSCustomObject]@{ Name = 'Frontend'; Process = $frontendProcess }
        )) {
            $service.Process.Refresh()
            if ($service.Process.HasExited) {
                [Console]::Error.WriteLine(
                    "ERROR: $($service.Name) stopped (exit code $($service.Process.ExitCode)). Stopping the other service."
                )
                $exitCode = 1
                break
            }
        }

        if ($exitCode -ne 0) {
            break
        }

        Start-Sleep -Seconds 1
    }
}
finally {
    Write-Host 'Stopping services...'
    Stop-ProcessTree -RootProcess $frontendProcess -ServiceName 'Frontend'
    Stop-ProcessTree -RootProcess $backendProcess -ServiceName 'Backend'
    Write-Host 'Service shutdown complete.'
}

if ($exitCode -ne 0) {
    exit $exitCode
}
