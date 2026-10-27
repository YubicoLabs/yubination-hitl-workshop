# Requires Windows PowerShell 5.1+; installs only this extracted package in place.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('Install', 'Preflight', 'Remove', 'RunHumanService')]
    [string]$Command,
    [Parameter(Mandatory=$true)][string]$ChromeUserDataDir
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$facts = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'installation.json') -Raw | ConvertFrom-Json
if (@($facts.PSObject.Properties.Name).Count -ne 2 -or
    @($facts.PSObject.Properties.Name | Where-Object { $_ -notin @('chromeExtensionId','nativeHosts') }).Count -or
    @($facts.nativeHosts.PSObject.Properties.Name).Count -ne 2 -or
    @($facts.nativeHosts.PSObject.Properties.Name | Where-Object { $_ -notin @('macos','windows') }).Count -or
    $facts.chromeExtensionId -isnot [string] -or $facts.chromeExtensionId -cnotmatch '^[a-p]{32}$' -or
    $facts.nativeHosts.macos -isnot [string] -or $facts.nativeHosts.macos -cnotmatch '^[a-z0-9_]+(?:\.[a-z0-9_]+)+$' -or
    $facts.nativeHosts.windows -isnot [string] -or $facts.nativeHosts.windows -cnotmatch '^[a-z0-9_]+(?:\.[a-z0-9_]+)+$') {
    throw 'Invalid installation facts.'
}
$nativeHost = $facts.nativeHosts.windows
$registryName = "Software\Google\Chrome\NativeMessagingHosts\$nativeHost"
$extensionId = $facts.chromeExtensionId
$inventoryName = '.previewsign-windows-package.json'
$payloadNames = @(
    'LICENSE', 'LICENSE-SCOPE.md', 'PROVENANCE.json', 'README.txt', 'install.ps1',
    'installation.json',
    'windows_service_launcher.ps1',
    'bin/sign-extension-host.exe', 'bin/sign-extension-service.exe',
    'notices/malloc_buf-MIT.txt', 'notices/malloc_buf-0.0.6.provenance.json',
    'extension/manifest.json', 'extension/workshop-origins.json',
    'extension/background.js', 'extension/content.js', 'extension/page.js',
    'extension/popup.html', 'extension/popup.js', 'extension/pin.html', 'extension/pin.js',
    'extension/pin-setup.html', 'extension/pin-setup.js', 'extension/pin-change.html',
    'extension/pin-change.js', 'extension/touch.html', 'extension/touch.js',
    'extension/select.html', 'extension/select.js'
)

function Assert-PlainPath([string]$Value) {
    if (-not [IO.Path]::IsPathRooted($Value) -or $Value.StartsWith('\\')) {
        throw 'Use an absolute local path.'
    }
    $full = [IO.Path]::GetFullPath($Value).TrimEnd('\')
    $cursor = $full
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'Symlink/reparse paths are not supported.'
            }
        }
        $cursor = [IO.Path]::GetDirectoryName($cursor)
    }
    return $full
}

function Get-Digest([string]$File) {
    $null = Assert-PlainPath $File
    if (-not (Test-Path -LiteralPath $File -PathType Leaf)) { throw 'Required package file missing.' }
    return (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-Names($Names, $Expected) {
    if (@($Names).Count -ne @($Expected).Count -or
        @(Compare-Object -ReferenceObject @($Expected) -DifferenceObject @($Names) -CaseSensitive).Count) {
        throw 'Package ownership inventory file set changed.'
    }
}

function Get-Registrations {
    foreach ($hive in @([Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryHive]::LocalMachine)) {
        foreach ($view in @([Microsoft.Win32.RegistryView]::Registry32, [Microsoft.Win32.RegistryView]::Registry64)) {
            $baseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, $view)
            try {
                $key = $baseKey.OpenSubKey($registryName)
                if ($null -ne $key) {
                    try {
                        [pscustomobject]@{ Hive=$hive; View=$view; Value=$key.GetValue('');
                            Names=@($key.GetValueNames()); Children=$key.SubKeyCount;
                            Kind= if ($key.GetValueNames() -contains '') { $key.GetValueKind('') } else { $null } }
                    } finally { $key.Dispose() }
                }
            } finally { $baseKey.Dispose() }
        }
    }
}

function Assert-OwnedRegistration($Entries, [string]$Manifest) {
    foreach ($entry in $Entries) {
        if ($entry.Hive -ne [Microsoft.Win32.RegistryHive]::CurrentUser -or
            $entry.Children -ne 0 -or
            @($entry.Names).Count -gt 1 -or
            (@($entry.Names).Count -eq 1 -and
                ($entry.Names[0] -cne '' -or $entry.Value -cne $Manifest -or
                 $entry.Kind -ne [Microsoft.Win32.RegistryValueKind]::String))) {
            throw 'Registration belongs to another installation or has changed.'
        }
    }
}

function Write-JsonNew([string]$File, $Value) {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($Value | ConvertTo-Json -Depth 20) + "`n")
    $stream = [IO.File]::Open($File, [IO.FileMode]::CreateNew)
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
}

try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Windows is required.' }
    $destination = Assert-PlainPath $PSScriptRoot
    $profile = Assert-PlainPath $ChromeUserDataDir
    if ($destination -eq $profile -or $destination.StartsWith($profile + '\', [StringComparison]::OrdinalIgnoreCase) -or
        $profile.StartsWith($destination + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Package and dedicated Chrome profile must not overlap.'
    }
    $manifestPath = Join-Path $destination 'native-host.json'
    $inventoryPath = Join-Path $destination $inventoryName
    $entries = @(Get-Registrations)
    if ($Command -eq 'Install') {
        if ($entries.Count -or (Test-Path -LiteralPath $profile) -or
            (Test-Path -LiteralPath $manifestPath) -or (Test-Path -LiteralPath $inventoryPath)) {
            throw 'Existing registration, installation or profile preserved. Use a fresh setup.'
        }
        $checksums = Get-Content -LiteralPath (Join-Path $destination 'checksums.json') -Raw | ConvertFrom-Json
        Assert-Names @($checksums.PSObject.Properties.Name) $payloadNames
        foreach ($name in $payloadNames) {
            if ((Get-Digest (Join-Path $destination $name)) -cne $checksums.$name) { throw 'Package checksum mismatch.' }
        }
        $extension = Get-Content -LiteralPath (Join-Path $destination 'extension/manifest.json') -Raw | ConvertFrom-Json
        $hash = [Security.Cryptography.SHA256]::Create()
        try { $keyHash = $hash.ComputeHash([Convert]::FromBase64String($extension.key)) } finally { $hash.Dispose() }
        $derivedId = -join ($keyHash[0..15] | ForEach-Object {
            [string][char](97 + ($_ -shr 4)) + [string][char](97 + ($_ -band 15))
        })
        if ($derivedId -cne $extensionId) { throw 'Extension identity mismatch.' }
        Write-JsonNew $manifestPath @{
            name=$nativeHost; description='PreviewSign Windows workshop helper';
            path=(Join-Path $destination 'bin/sign-extension-host.exe'); type='stdio';
            allowed_origins=@("chrome-extension://$extensionId/")
        }
        $owned = @{}
        foreach ($name in @($payloadNames) + @('checksums.json', 'native-host.json')) {
            $owned[$name] = Get-Digest (Join-Path $destination $name)
        }
        Write-JsonNew $inventoryPath @{ destination=$destination; profile=$profile; files=$owned }
        # Recovery inventory is persisted before registry publication.
        $baseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey(
            [Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryView]::Registry64)
        try {
            $key = $baseKey.CreateSubKey($registryName)
            try { $key.SetValue('', $manifestPath, [Microsoft.Win32.RegistryValueKind]::String) }
            finally { $key.Dispose() }
        } finally { $baseKey.Dispose() }
        Write-Output "Installed. Load unpacked extension from: $(Join-Path $destination 'extension')"
        Write-Output "Dedicated Chrome profile: $profile"
        exit 0
    }
    $state = Get-Content -LiteralPath $inventoryPath -Raw | ConvertFrom-Json
    if ($state.destination -cne $destination -or $state.profile -cne $profile) { throw 'Installation identity mismatch.' }
    Assert-Names @($state.files.PSObject.Properties.Name) (@($payloadNames) + @('checksums.json', 'native-host.json'))
    foreach ($property in $state.files.PSObject.Properties) {
        if ((Get-Digest (Join-Path $destination $property.Name)) -cne $property.Value) { throw 'Owned file changed; preserve for inspection.' }
    }
    Assert-OwnedRegistration $entries $manifestPath
    if ($Command -eq 'Remove') {
        foreach ($entry in $entries) {
            $baseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey($entry.Hive, $entry.View)
            try { $baseKey.DeleteSubKey($registryName, $false) } finally { $baseKey.Dispose() }
        }
        foreach ($name in @($payloadNames) + @('checksums.json', 'native-host.json', $inventoryName)) {
            [IO.File]::Delete((Join-Path $destination $name))
        }
        foreach ($folder in @('bin', 'extension', 'notices', '')) {
            $directory = if ($folder) { Join-Path $destination $folder } else { $destination }
            if ((Test-Path -LiteralPath $directory) -and @([IO.Directory]::EnumerateFileSystemEntries($directory)).Count -eq 0) {
                [IO.Directory]::Delete($directory, $false)
            }
        }
        Write-Output 'Owned registration and package files removed. Chrome profile and unrelated files preserved.'
    } else {
        if (-not $entries.Count -or @($entries | Where-Object { $_.Value -cne $manifestPath }).Count) {
            throw 'Owned registration missing; install before using the helper.'
        }
        if ($Command -eq 'RunHumanService') {
            Write-Output 'Human stage: keep this terminal open. Only the temporary helper requests UAC. Supply PIN/touch yourself.'
            # A separate short-lived controller is necessary: an interactive
            # shell survives Ctrl+C, and must not keep the elevated helper alive.
            & (Get-Process -Id $PID).Path -NoProfile -File (Join-Path $destination 'windows_service_launcher.ps1') -ServiceExecutable (Join-Path $destination 'bin/sign-extension-service.exe') -ServiceSha256 $state.files.'bin/sign-extension-service.exe' -HostSha256 $state.files.'bin/sign-extension-host.exe'
            if ($LASTEXITCODE) { throw 'Signing helper launch failed or was declined.' }
        } else { Write-Output 'Owned package and registration match. Check helper health in Chrome next.' }
    }
} catch {
    Write-Error $_
    exit 1
}
