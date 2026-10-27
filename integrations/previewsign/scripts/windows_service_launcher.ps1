# A dedicated, unelevated controller. No policy bypass or persistent installation.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ServiceExecutable,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ServiceSha256,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$HostSha256,
    [switch]$ValidateOnly
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$locks = @()
try {
    if ($ServiceExecutable -notmatch '^[A-Za-z]:[\\/]' -or $ServiceExecutable.StartsWith('\\')) {
        throw 'An absolute local service executable is required.'
    }
    $principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run the workshop and controller without elevation. Only the helper requests UAC.'
    }
    $service = [IO.Path]::GetFullPath($ServiceExecutable)
    if ([IO.Path]::GetFileName($service) -cne 'sign-extension-service.exe') { throw 'Unexpected helper filename.' }
    $directory = [IO.Path]::GetDirectoryName($service)
    $hostFile = Join-Path $directory 'sign-extension-host.exe'
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class WorkshopDirectoryLock {
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern SafeFileHandle CreateFileW(string name, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool GetNamedPipeServerProcessId(SafeFileHandle pipe, out uint processId);
}
'@
    $ancestors = @()
    $cursor = $directory
    while ($cursor) { $ancestors = @($cursor) + $ancestors; $cursor = [IO.Path]::GetDirectoryName($cursor) }
    foreach ($parentDirectory in $ancestors) {
        $directoryHandle = [WorkshopDirectoryLock]::CreateFileW($parentDirectory, 2147483648, 1, [IntPtr]::Zero, 3, 0x02200000, [IntPtr]::Zero)
        if ($directoryHandle.IsInvalid) { $directoryHandle.Dispose(); throw 'Cannot lock package parent directory.' }
        $locks += $directoryHandle
        if ((Get-Item -LiteralPath $parentDirectory -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'Reparse package parent directory rejected.'
        }
    }
    foreach ($file in @($service, $hostFile)) {
        $cursor = $file
        while ($cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'Reparse executable paths are not allowed.'
            }
            $cursor = [IO.Path]::GetDirectoryName($cursor)
        }
        $locks += [IO.File]::Open($file, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    }
    if ((Get-FileHash -LiteralPath $service -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ServiceSha256 -or
        (Get-FileHash -LiteralPath $hostFile -Algorithm SHA256).Hash.ToLowerInvariant() -cne $HostSha256) {
        throw 'Helper/host hash differs from the validated installation.'
    }
    if ($ValidateOnly) { Write-Output 'Launcher binary checks passed; no elevation requested.'; exit 0 }
    if ([IO.Directory]::GetFiles('\\.\pipe\') -contains '\\.\pipe\yubico-previewsign-workshop') {
        throw 'An existing workshop pipe is preserved. Stop its owner before continuing.'
    }
    Write-Output 'UAC: consent only to this reviewed workshop signing helper. Chrome stays unelevated.'
    $child = Start-Process -FilePath $service -Verb RunAs -ArgumentList @('--gui', '--controller-pid', "$PID") -WorkingDirectory ([Environment]::GetFolderPath('System')) -WindowStyle Hidden -PassThru
    $ready = $false
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    while ([DateTime]::UtcNow -lt $deadline -and -not $child.HasExited) {
        if ([IO.Directory]::GetFiles('\\.\pipe\') -contains '\\.\pipe\yubico-previewsign-workshop') {
            # Identification-only connection; no request, credential or PIN bytes.
            $pipe = [WorkshopDirectoryLock]::CreateFileW('\\.\pipe\yubico-previewsign-workshop', 0, 0, [IntPtr]::Zero, 3, 0x00110000, [IntPtr]::Zero)
            try {
                [uint32]$serverId = 0
                if (-not $pipe.IsInvalid -and [WorkshopDirectoryLock]::GetNamedPipeServerProcessId($pipe, [ref]$serverId) -and
                    $serverId -eq $child.Id -and -not $child.HasExited) { $ready = $true; break }
            } finally { $pipe.Dispose() }
        }
        Start-Sleep -Milliseconds 100
    }
    if (-not $ready) { throw 'Helper did not become ready; no ceremony was started.' }
    Write-Output "WORKSHOP_HELPER_READY $($child.Id)"
    while (-not $child.WaitForExit(500)) { }
    if ($child.ExitCode -ne 0) { throw 'Signing helper exited with failure.' }
} catch {
    if ($ValidateOnly) { Write-Error $_; exit 1 }
    Write-Error 'Workshop helper launch failed or was declined. No automatic retry.'
    exit 1
} finally {
    foreach ($lockedFile in $locks) { $lockedFile.Dispose() }
    # This dedicated process exits at script end. The elevated helper's held
    # controller handle detects exit, then self-terminates (also capped at 600s).
}
