[CmdletBinding()]
param()

$installerWasDotSourced = $MyInvocation.InvocationName -eq "."
$installerImplementation = {
param([bool]$RunInstaller)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$LatestReleaseApi = "https://api.github.com/repos/yaatv/yaatv/releases/latest"
$ExpectedSigningKeyFingerprint = "89687756391589496E71E6665314FF77F9EE3C59"
$WindowsReleaseTargets = @{
    x64 = @{
        AssetName = "yaatv-windows-x64.exe"
        Packaging = "onefile"
    }
}

function ConvertTo-NormalizedArchitecture {
    param([Parameter(Mandatory = $true)][string]$Architecture)

    switch -Regex ($Architecture.Trim().ToLowerInvariant()) {
        "^(amd64|x86_64|x64)$" { return "x64" }
        "^(arm64|aarch64)$" { return "arm64" }
        "^(x86|i[3-6]86)$" { return "x86" }
        default { return $Architecture.Trim().ToLowerInvariant() }
    }
}

function Get-WindowsArchitecture {
    $architecture = $null
    try {
        $architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    }
    catch {
        $architecture = [Environment]::GetEnvironmentVariable("PROCESSOR_ARCHITEW6432")
        if ([string]::IsNullOrWhiteSpace($architecture)) {
            $architecture = [Environment]::GetEnvironmentVariable("PROCESSOR_ARCHITECTURE")
        }
    }

    if ([string]::IsNullOrWhiteSpace($architecture) -or $architecture -eq "Unknown") {
        $architecture = [Environment]::GetEnvironmentVariable("PROCESSOR_ARCHITEW6432")
        if ([string]::IsNullOrWhiteSpace($architecture)) {
            $architecture = [Environment]::GetEnvironmentVariable("PROCESSOR_ARCHITECTURE")
        }
    }
    if ([string]::IsNullOrWhiteSpace($architecture) -or $architecture -eq "Unknown") {
        throw "Could not determine the Windows operating-system architecture."
    }
    return ConvertTo-NormalizedArchitecture $architecture
}

function Get-WindowsReleaseTarget {
    param([Parameter(Mandatory = $true)][string]$Architecture)

    $normalized = ConvertTo-NormalizedArchitecture $Architecture
    if (-not $WindowsReleaseTargets.ContainsKey($normalized)) {
        throw "Windows architecture '$Architecture' is not supported by a published yaatv release. No compatible installer is available."
    }
    return $WindowsReleaseTargets[$normalized]
}

function ConvertTo-StableVersion {
    param([Parameter(Mandatory = $true)][string]$Tag)

    $match = [regex]::Match($Tag, "^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
    if (-not $match.Success) {
        throw "GitHub returned a release tag that is not a stable yaatv version: '$Tag'."
    }
    try {
        return [version]::Parse("$($match.Groups[1].Value).$($match.Groups[2].Value).$($match.Groups[3].Value)")
    }
    catch {
        throw "GitHub returned an invalid yaatv release version: '$Tag'."
    }
}

function Assert-LatestStableRelease {
    param([Parameter(Mandatory = $true)][object]$Release)

    if ($null -eq $Release) {
        throw "GitHub returned malformed release metadata or a draft release."
    }
    $draftProperty = $Release.PSObject.Properties["draft"]
    $prereleaseProperty = $Release.PSObject.Properties["prerelease"]
    $tagProperty = $Release.PSObject.Properties["tag_name"]
    $assetsProperty = $Release.PSObject.Properties["assets"]
    if ($null -eq $draftProperty -or $draftProperty.Value -isnot [bool] -or $draftProperty.Value) {
        throw "GitHub returned malformed release metadata or a draft release."
    }
    if ($null -eq $prereleaseProperty -or $prereleaseProperty.Value -isnot [bool]) {
        throw "GitHub returned malformed release metadata; a prerelease status was expected."
    }
    if ($prereleaseProperty.Value) {
        throw "GitHub returned a prerelease; the installer requires the latest stable release."
    }
    if ($null -eq $tagProperty -or $tagProperty.Value -isnot [string] -or $null -eq $assetsProperty -or $assetsProperty.Value -isnot [array]) {
        throw "GitHub returned malformed release metadata; a stable tag and asset list were expected."
    }

    $version = ConvertTo-StableVersion $tagProperty.Value
    return [pscustomobject]@{
        Tag = $tagProperty.Value
        Version = $version
        Assets = $assetsProperty.Value
    }
}

function Get-HttpStatusCode {
    param([Parameter(Mandatory = $true)][System.Management.Automation.ErrorRecord]$ErrorRecord)

    try {
        return [int]$ErrorRecord.Exception.Response.StatusCode
    }
    catch {
        return $null
    }
}

function Get-LatestStableRelease {
    try {
    $response = Invoke-RestMethod `
            -Uri $LatestReleaseApi `
            -Method Get `
            -Headers @{
                Accept = "application/vnd.github+json"
                "X-GitHub-Api-Version" = "2022-11-28"
            } `
            -UserAgent "yaatv-installer" `
            -TimeoutSec 30 `
            -ErrorAction Stop
    }
    catch {
        $status = Get-HttpStatusCode $_
        if ($status -eq 404) {
            throw "GitHub did not find a published stable yaatv release. No release was installed."
        }
        if ($status -eq 403 -or $status -eq 429) {
            throw "GitHub refused the release lookup, possibly because of API rate limiting. Wait a few minutes and try again."
        }
        throw "Could not read the latest yaatv release from GitHub: $($_.Exception.Message)"
    }

    return Assert-LatestStableRelease $response
}

function Assert-OfficialReleaseAssetUrl {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Tag,
        [Parameter(Mandatory = $true)][string]$AssetName
    )

    $uri = $null
    if (-not [uri]::TryCreate($Url, [System.UriKind]::Absolute, [ref]$uri)) {
        throw "GitHub returned a malformed download URL for '$AssetName'."
    }
    $expectedPath = "/yaatv/yaatv/releases/download/$Tag/$AssetName"
    if (
        $uri.Scheme -cne "https" -or
        $uri.Host -ne "github.com" -or
        -not $uri.IsDefaultPort -or
        $uri.UserInfo -or
        $uri.Query -or
        $uri.Fragment -or
        $uri.AbsolutePath -cne $expectedPath
    ) {
        throw "GitHub returned an unexpected download URL for '$AssetName'. The installer only accepts official yaatv release assets."
    }
    return $uri
}

function Get-ReleaseAsset {
    param(
        [Parameter(Mandatory = $true)][object]$Release,
        [Parameter(Mandatory = $true)][string]$AssetName
    )

    $matches = @($Release.Assets | Where-Object {
        if ($null -eq $_) {
            return $false
        }
        $nameProperty = $_.PSObject.Properties["name"]
        $null -ne $nameProperty -and $nameProperty.Value -is [string] -and $nameProperty.Value -ceq $AssetName
    })
    if ($matches.Count -eq 0) {
        throw "Release $($Release.Tag) does not contain the expected asset '$AssetName'. No files were installed."
    }
    if ($matches.Count -ne 1) {
        throw "Release $($Release.Tag) contains multiple assets named '$AssetName'. The installer stopped without choosing one."
    }

    $asset = $matches[0]
    $sizeProperty = $asset.PSObject.Properties["size"]
    $urlProperty = $asset.PSObject.Properties["browser_download_url"]
    $size = 0L
    if (
        $null -eq $sizeProperty -or
        $sizeProperty.Value -isnot [ValueType] -or
        -not [long]::TryParse([string]$sizeProperty.Value, [ref]$size) -or
        $size -le 0 -or
        $null -eq $urlProperty -or
        $urlProperty.Value -isnot [string]
    ) {
        throw "Release metadata for '$AssetName' is incomplete or invalid."
    }

    $url = Assert-OfficialReleaseAssetUrl $urlProperty.Value $Release.Tag $AssetName
    return [pscustomobject]@{
        Name = $AssetName
        Size = $size
        Url = $url.AbsoluteUri
    }
}

function Get-ResponseUri {
    param([Parameter(Mandatory = $true)][object]$Response)

    $baseResponse = $Response.BaseResponse
    if ($null -eq $baseResponse) {
        return $null
    }
    $responseUriProperty = $baseResponse.PSObject.Properties["ResponseUri"]
    if ($null -ne $responseUriProperty -and $null -ne $responseUriProperty.Value) {
        return [uri]$responseUriProperty.Value
    }
    $requestMessageProperty = $baseResponse.PSObject.Properties["RequestMessage"]
    if ($null -ne $requestMessageProperty -and $null -ne $requestMessageProperty.Value) {
        $requestUriProperty = $requestMessageProperty.Value.PSObject.Properties["RequestUri"]
        if ($null -ne $requestUriProperty -and $null -ne $requestUriProperty.Value) {
            return [uri]$requestUriProperty.Value
        }
    }
    return $null
}

function Invoke-OfficialDownload {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][string[]]$AllowedHosts,
        [Parameter(Mandatory = $true)][string]$Description
    )

    try {
        $response = Invoke-WebRequest `
            -Uri $Url `
            -Method Get `
            -OutFile $Destination `
            -PassThru `
            -UseBasicParsing `
            -MaximumRedirection 3 `
            -TimeoutSec 300 `
            -ErrorAction Stop
    }
    catch {
        $status = Get-HttpStatusCode $_
        if ($status -eq 404) {
            throw "GitHub did not provide the expected $Description. No files were installed."
        }
        if ($status -eq 403 -or $status -eq 429) {
            throw "GitHub refused the $Description download, possibly because of rate limiting. Wait a few minutes and try again."
        }
        throw "Could not download the $Description from GitHub: $($_.Exception.Message)"
    }

    $file = Get-Item -LiteralPath $Destination -ErrorAction SilentlyContinue
    if ($null -eq $file -or $file.PSIsContainer -or $file.Length -le 0) {
        throw "The $Description download was empty or incomplete. No files were installed."
    }

    $finalUri = Get-ResponseUri $response
    if ($null -eq $finalUri) {
        throw "Could not verify the final HTTPS destination for the $Description download. The installer stopped."
    }
    if (
        $finalUri.Scheme -cne "https" -or
        -not $finalUri.IsDefaultPort -or
        $finalUri.UserInfo -or
        $finalUri.Host -notin $AllowedHosts
    ) {
        throw "GitHub redirected the $Description download outside the approved HTTPS GitHub hosts. The installer stopped."
    }
    return $file
}

function Get-ManifestDigest {
    param(
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$AssetName
    )

    $manifestFile = Get-Item -LiteralPath $ManifestPath
    if ($manifestFile.Length -le 0 -or $manifestFile.Length -gt 1048576) {
        throw "The SHA256SUMS file is empty or unexpectedly large. The release manifest is invalid."
    }
    try {
        $manifest = [IO.File]::ReadAllText($ManifestPath, [Text.Encoding]::UTF8)
    }
    catch {
        throw "Could not read the downloaded SHA256SUMS file: $($_.Exception.Message)"
    }

    $digests = @()
    foreach ($line in ($manifest -split "`r?`n")) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        $match = [regex]::Match($line, "^([0-9a-fA-F]{64})\s+\*?([A-Za-z0-9._-]+)$")
        if (-not $match.Success) {
            throw "The SHA256SUMS file contains a malformed entry. The release manifest is invalid."
        }
        if ($match.Groups[2].Value -ceq $AssetName) {
            $digests += $match.Groups[1].Value.ToLowerInvariant()
        }
    }
    if ($digests.Count -eq 0) {
        throw "SHA256SUMS does not contain an entry for '$AssetName'. The release manifest is incomplete."
    }
    if ($digests.Count -ne 1) {
        throw "SHA256SUMS contains multiple entries for '$AssetName'. The release manifest is ambiguous."
    }
    return $digests[0]
}

function Assert-TrustedReleaseSignature {
    param(
        [Parameter(Mandatory = $true)][string[]]$KeyOutput,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$ImportOutput,
        [Parameter(Mandatory = $true)][string[]]$VerificationOutput
    )

    $publicKeyCount = 0
    $primaryFingerprint = $null
    $awaitingPrimaryFingerprint = $false
    foreach ($line in $KeyOutput) {
        $fields = ([string]$line).Split(":")
        if ($fields[0] -eq "pub") {
            $publicKeyCount++
            $awaitingPrimaryFingerprint = $true
        }
        elseif ($fields[0] -eq "fpr" -and $awaitingPrimaryFingerprint -and $fields.Count -gt 9) {
            if ($publicKeyCount -eq 1) {
                $primaryFingerprint = $fields[9].ToUpperInvariant()
            }
            $awaitingPrimaryFingerprint = $false
        }
    }
    if ($publicKeyCount -ne 1 -or $primaryFingerprint -cne $ExpectedSigningKeyFingerprint) {
        throw "The release public key does not contain exactly the trusted YAATV primary key from SECURITY.md. No files were installed."
    }

    $importedKeyLines = @(
        $ImportOutput | Where-Object { ([string]$_) -match "^\[GNUPG:\] IMPORT_OK\s+\d+\s+[0-9A-Fa-f]{40,64}\s*$" }
    )
    if ($importedKeyLines.Count -ne 1) {
        throw "GPG did not import exactly one YAATV release key. No files were installed."
    }
    $importedKeyFields = ([string]$importedKeyLines[0]) -split "\s+"
    if ($importedKeyFields[3].ToUpperInvariant() -cne $ExpectedSigningKeyFingerprint) {
        throw "GPG did not import the trusted YAATV release key. No files were installed."
    }

    $invalidSignatureStatusLines = @(
        $VerificationOutput | Where-Object {
            ([string]$_) -match "^\[GNUPG:\] (?:BADSIG|ERRSIG|EXPSIG|EXPKEYSIG|REVKEYSIG|KEYREVOKED|SIGEXPIRED)(?:\s|$)"
        }
    )
    if ($invalidSignatureStatusLines.Count -gt 0) {
        throw "The SHA256SUMS signature is invalid, expired, or revoked. No files were installed."
    }

    $validSignatureLines = @(
        $VerificationOutput | Where-Object { ([string]$_) -match "^\[GNUPG:\] VALIDSIG\s+" }
    )
    if ($validSignatureLines.Count -ne 1) {
        throw "GPG did not report exactly one valid SHA256SUMS signature. No files were installed."
    }

    $statusFields = ([string]$validSignatureLines[0]) -split "\s+"
    $signingFingerprint = $statusFields[2].ToUpperInvariant()
    $signaturePrimaryFingerprint = $null
    if ($statusFields.Count -ge 12) {
        $signaturePrimaryFingerprint = $statusFields[11].ToUpperInvariant()
    }
    if (
        $signingFingerprint -cne $ExpectedSigningKeyFingerprint -and
        $signaturePrimaryFingerprint -cne $ExpectedSigningKeyFingerprint
    ) {
        throw "The SHA256SUMS signature was not made by the trusted YAATV release key. No files were installed."
    }
}

function Invoke-OpenPgpProcess {
    param(
        [Parameter(Mandatory = $true)][string]$ExecutablePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $previousLastExitCodeVariable = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
    $previousLastExitCode = 0
    if ($null -ne $previousLastExitCodeVariable -and $null -ne $previousLastExitCodeVariable.Value) {
        $previousLastExitCode = [int]$previousLastExitCodeVariable.Value
    }
    $exitCode = 0
    $output = @()
    try {
        # Windows PowerShell 5.1 promotes native stderr to errors under Stop; GPG writes normal status there.
        $ErrorActionPreference = "Continue"
        $output = @(& $ExecutablePath @Arguments 2>&1 | ForEach-Object { [string]$_ })
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        $global:LASTEXITCODE = $previousLastExitCode
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = [string[]]$output
    }
}

function Test-ReleaseSignature {
    param(
        [Parameter(Mandatory = $true)][object]$Release,
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$TemporaryDirectory
    )

    $gpg = Get-Command gpg -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $gpg) {
        Write-Host "GPG was not found. The installer will check SHA-256 against the GitHub release manifest, but will not verify its PGP signature."
        return $false
    }

    $signatureAsset = Get-ReleaseAsset $Release "SHA256SUMS.asc"
    $signaturePath = Join-Path $TemporaryDirectory "SHA256SUMS.asc"
    [void](Invoke-OfficialDownload `
        -Url $signatureAsset.Url `
        -Destination $signaturePath `
        -AllowedHosts @("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com") `
        -Description "SHA256SUMS signature")

    $publicKeyUrl = "https://raw.githubusercontent.com/yaatv/yaatv/$($Release.Tag)/public.key"
    $publicKeyPath = Join-Path $TemporaryDirectory "public.key"
    [void](Invoke-OfficialDownload `
        -Url $publicKeyUrl `
        -Destination $publicKeyPath `
        -AllowedHosts @("raw.githubusercontent.com") `
        -Description "YAATV release public key")
    $publicKey = Get-Item -LiteralPath $publicKeyPath
    if ($publicKey.Length -gt 1048576) {
        throw "The YAATV public key is unexpectedly large. The installer stopped."
    }

    $gpgPath = $gpg.Path
    if ([string]::IsNullOrWhiteSpace($gpgPath)) {
        $gpgPath = $gpg.Source
    }

    $gpgHome = Join-Path $TemporaryDirectory "gpg-home"
    [void][IO.Directory]::CreateDirectory($gpgHome)

    $keyResult = Invoke-OpenPgpProcess $gpgPath @(
        "--batch", "--no-options", "--homedir", $gpgHome, "--with-colons", "--show-keys", $publicKeyPath
    )
    if ($keyResult.ExitCode -ne 0) {
        throw "GPG could not read the public key from release $($Release.Tag)."
    }
    $keyOutput = $keyResult.Output

    $importResult = Invoke-OpenPgpProcess $gpgPath @(
        "--batch", "--no-options", "--no-autostart", "--no-auto-key-retrieve", "--homedir", $gpgHome, "--status-fd", "1", "--import", $publicKeyPath
    )

    # The isolated home prevents use of the user's keyring. Full gpg verification reports key and signature expiry/revocation statuses, unlike gpgv.
    $verificationResult = Invoke-OpenPgpProcess $gpgPath @(
        "--batch", "--no-options", "--no-autostart", "--no-auto-key-retrieve", "--homedir", $gpgHome, "--status-fd", "1", "--verify", $signaturePath, $ManifestPath
    )
    if ($verificationResult.ExitCode -ne 0) {
        throw "The SHA256SUMS PGP signature did not verify with the trusted YAATV key. No files were installed."
    }
    # Some Windows GPG builds return nonzero after IMPORT_OK when the agent cannot start; accept only after the pinned key and full signature status both check out.
    Assert-TrustedReleaseSignature $keyOutput $importResult.Output $verificationResult.Output
    Write-Host "Verified the SHA256SUMS PGP signature with the YAATV release key."
    return $true
}

function Get-ComparableWindowsPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $value = $Path.Trim()
    if ($value.Length -ge 2 -and $value[0] -eq '"' -and $value[$value.Length - 1] -eq '"') {
        $value = $value.Substring(1, $value.Length - 2)
    }
    $value = [Environment]::ExpandEnvironmentVariables($value)
    try {
        $value = [IO.Path]::GetFullPath($value)
    }
    catch {
        return $value.TrimEnd([char[]]@("\", "/")).ToUpperInvariant()
    }
    $root = [IO.Path]::GetPathRoot($value)
    if ($value.Length -gt $root.Length) {
        $value = $value.TrimEnd([char[]]@("\", "/"))
    }
    return $value.ToUpperInvariant()
}

function Test-PathContainsEntry {
    param(
        [AllowEmptyString()][string]$PathValue,
        [Parameter(Mandatory = $true)][string]$Entry
    )

    $target = Get-ComparableWindowsPath $Entry
    foreach ($component in ($PathValue -split ";")) {
        if (-not [string]::IsNullOrWhiteSpace($component) -and (Get-ComparableWindowsPath $component) -ceq $target) {
            return $true
        }
    }
    return $false
}

function Get-FreshWindowsPath {
    param(
        [AllowNull()][AllowEmptyString()][string]$MachinePath,
        [AllowNull()][AllowEmptyString()][string]$UserPath,
        [Parameter(Mandatory = $true)][string]$InstallDirectory
    )

    if ($null -eq $MachinePath) {
        $MachinePath = ""
    }
    if ($null -eq $UserPath) {
        $UserPath = ""
    }
    if (-not (Test-PathContainsEntry $UserPath $InstallDirectory)) {
        throw "The managed install directory '$InstallDirectory' is not present in the persisted current-user PATH. The executable may be installed, but a new terminal will not find it. Check current-user PATH permissions and rerun the installer."
    }

    $expandedMachinePath = [Environment]::ExpandEnvironmentVariables($MachinePath)
    $expandedUserPath = [Environment]::ExpandEnvironmentVariables($UserPath)
    if ([string]::IsNullOrEmpty($expandedMachinePath)) {
        return $expandedUserPath
    }
    if ([string]::IsNullOrEmpty($expandedUserPath)) {
        return $expandedMachinePath
    }
    return "$expandedMachinePath;$expandedUserPath"
}

function Get-InstallationPaths {
    param([AllowEmptyString()][string]$LocalAppData)

    if ([string]::IsNullOrWhiteSpace($LocalAppData)) {
        throw "LOCALAPPDATA is not set. The installer cannot choose a per-user installation directory."
    }
    $pathRoot = [IO.Path]::GetPathRoot($LocalAppData)
    $isDriveAbsolute = $pathRoot -match "^[A-Za-z]:\\$"
    $isUncAbsolute = $pathRoot -match "^\\\\[^\\]+\\[^\\]+\\?$"
    if (
        (-not $isDriveAbsolute -and -not $isUncAbsolute) -or
        $LocalAppData.Contains(";") -or
        $LocalAppData.Contains("`r") -or
        $LocalAppData.Contains("`n") -or
        $LocalAppData.Contains([char]0)
    ) {
        throw "LOCALAPPDATA must be a fully qualified absolute path without PATH separators or control characters."
    }

    $root = [IO.Path]::GetFullPath($LocalAppData)
    $normalizedRoot = $root.TrimEnd([char[]]@("\", "/"))
    $normalizedPathRoot = $pathRoot.TrimEnd([char[]]@("\", "/"))
    if ([string]::Equals($normalizedRoot, $normalizedPathRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "LOCALAPPDATA must point inside a user profile, not at a volume or share root."
    }
    $directory = [IO.Path]::Combine($root, "Programs", "yaatv", "bin")
    return [pscustomobject]@{
        Directory = $directory
        Executable = [IO.Path]::Combine($directory, "yaatv.exe")
    }
}

function Get-ExecutableVersion {
    param([Parameter(Mandatory = $true)][string]$ExecutablePath)

    if (-not (Test-Path -LiteralPath $ExecutablePath -PathType Leaf)) {
        throw "The yaatv executable was not found at '$ExecutablePath'."
    }
    $output = @(& $ExecutablePath --version 2>&1)
    $exitCode = $LASTEXITCODE
    $text = ($output | ForEach-Object { [string]$_ }) -join [Environment]::NewLine
    if ($exitCode -ne 0) {
        throw "Running '$ExecutablePath --version' failed with exit code $exitCode. $text"
    }
    $match = [regex]::Match($text, "(?m)^\s*yaatv\s+(?<version>v?(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))\s*$")
    if (-not $match.Success) {
        throw "'$ExecutablePath --version' did not return a stable yaatv version. Output: $text"
    }
    return ConvertTo-StableVersion $match.Groups["version"].Value
}

function Assert-NoConflictingCommand {
    param([Parameter(Mandatory = $true)][string]$ManagedExecutable)

    $commands = @(Get-Command yaatv -CommandType Application -All -ErrorAction SilentlyContinue)
    if ($commands.Count -eq 0) {
        return
    }
    $firstPath = $commands[0].Path
    if ([string]::IsNullOrWhiteSpace($firstPath)) {
        $firstPath = $commands[0].Source
    }
    if ([string]::IsNullOrWhiteSpace($firstPath) -or (Get-ComparableWindowsPath $firstPath) -cne (Get-ComparableWindowsPath $ManagedExecutable)) {
        throw "Another yaatv command is earlier on PATH: '$firstPath'. Resolve that installation before installing here so 'yaatv --version' will not select the wrong copy."
    }
}

function Get-AvailableBytes {
    param([Parameter(Mandatory = $true)][string]$Path)

    try {
        $fullPath = [IO.Path]::GetFullPath($Path)
        $root = [IO.Path]::GetPathRoot($fullPath)
        if ([string]::IsNullOrWhiteSpace($root)) {
            return $null
        }
        $drive = New-Object -TypeName System.IO.DriveInfo -ArgumentList $root
        if ($drive.IsReady) {
            return [long]$drive.AvailableFreeSpace
        }
    }
    catch {
        return $null
    }
    return $null
}

function Assert-SufficientDiskSpace {
    param(
        [Parameter(Mandatory = $true)][string]$InstallDirectory,
        [Parameter(Mandatory = $true)][string]$TemporaryDirectory,
        [Parameter(Mandatory = $true)][long]$AssetSize
    )

    $reserve = [long]10485760
    $installRoot = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($InstallDirectory))
    $temporaryRoot = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($TemporaryDirectory))
    if ((Get-ComparableWindowsPath $installRoot) -ceq (Get-ComparableWindowsPath $temporaryRoot)) {
        $required = ($AssetSize * [long]2) + $reserve
        $available = Get-AvailableBytes $InstallDirectory
        if ($null -ne $available -and $available -lt $required) {
            throw "There is not enough free space on '$installRoot' to download and prepare the yaatv release. Free space and try again."
        }
        return
    }

    foreach ($path in @($InstallDirectory, $TemporaryDirectory)) {
        $available = Get-AvailableBytes $path
        if ($null -ne $available -and $available -lt ($AssetSize + $reserve)) {
            throw "There is not enough free space on '$([IO.Path]::GetPathRoot([IO.Path]::GetFullPath($path)) )' to prepare the yaatv release. Free space and try again."
        }
    }
}

function Invoke-VersionProcess {
    param(
        [Parameter(Mandatory = $true)][string]$ExecutablePath,
        [Parameter(Mandatory = $true)][string]$Arguments,
        [Parameter(Mandatory = $true)][string]$PathValue,
        [Parameter(Mandatory = $true)][string]$Description
    )

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $ExecutablePath
    $startInfo.Arguments = $Arguments
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.EnvironmentVariables["PATH"] = $PathValue

    $process = $null
    try {
        $process = [System.Diagnostics.Process]::Start($startInfo)
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        $exitCode = $process.ExitCode
    }
    catch {
        throw "$Description could not start: $($_.Exception.Message)"
    }
    finally {
        if ($null -ne $process) {
            $process.Dispose()
        }
    }

    if ($exitCode -ne 0) {
        throw "$Description failed with exit code $exitCode. $($stdout.Trim()) $($stderr.Trim())"
    }
    return (($stdout + [Environment]::NewLine + $stderr).Trim())
}

function Assert-FreshPathCommand {
    param(
        [Parameter(Mandatory = $true)][string]$ManagedExecutable,
        [Parameter(Mandatory = $true)][version]$ExpectedVersion,
        [Parameter(Mandatory = $true)][string]$PathValue
    )

    $wherePath = Join-Path $env:WINDIR "System32\where.exe"
    $whereOutput = Invoke-VersionProcess `
        -ExecutablePath $wherePath `
        -Arguments "yaatv" `
        -PathValue $PathValue `
        -Description "Fresh PATH lookup for yaatv"
    $resolvedPath = ($whereOutput -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1).Trim()
    if ([string]::IsNullOrWhiteSpace($resolvedPath)) {
        throw "PATH installation is incomplete: a fresh process could not resolve 'yaatv'. Open a new terminal after correcting the current-user PATH."
    }
    if ((Get-ComparableWindowsPath $resolvedPath) -cne (Get-ComparableWindowsPath $ManagedExecutable)) {
        throw "PATH installation is incomplete: a fresh process resolves 'yaatv' to '$resolvedPath', not the managed installation at '$ManagedExecutable'. Resolve the conflict and try again."
    }

    $commandOutput = Invoke-VersionProcess `
        -ExecutablePath (Join-Path $env:WINDIR "System32\cmd.exe") `
        -Arguments "/d /c yaatv --version" `
        -PathValue $PathValue `
        -Description "Fresh PATH command verification"
    $versionMatch = [regex]::Match($commandOutput, "(?m)^\s*yaatv\s+(?<version>v?(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))\s*$")
    if (-not $versionMatch.Success) {
        throw "PATH installation is incomplete: 'yaatv --version' did not return a yaatv version from a fresh process. Output: $commandOutput"
    }
    $pathVersion = ConvertTo-StableVersion $versionMatch.Groups["version"].Value
    if ($pathVersion -ne $ExpectedVersion) {
        throw "PATH installation is incomplete: 'yaatv --version' resolved to version $pathVersion; expected $ExpectedVersion."
    }
}

function Invoke-OneFileInstallation {
    param(
        [Parameter(Mandatory = $true)][string]$CandidatePath,
        [Parameter(Mandatory = $true)][string]$InstallExecutable
    )

    $output = @(& $CandidatePath --install 2>&1)
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        $diagnostic = ($output | ForEach-Object { [string]$_ }) -join [Environment]::NewLine
        if ($diagnostic -match "(?i)(being used by another process|used by another process|sharing violation|winerror 32)") {
            throw "The installed yaatv executable appears to be in use. Close yaatv and rerun the installer. The existing file was preserved."
        }
        if ($diagnostic -match "(?i)could not update the current-user path") {
            throw "The candidate executable may have been copied to '$InstallExecutable', but the current-user PATH update failed. Check PATH permissions before rerunning."
        }
        throw "The verified release executable could not install itself for the current user. Check '$InstallExecutable' and the current-user PATH, then try again. $diagnostic"
    }
    foreach ($line in $output) {
        Write-Host ([string]$line)
    }
}

function Invoke-YaAtvInstaller {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw "install.ps1 supports Windows only. Use the installation method documented for your operating system."
    }

    $architecture = Get-WindowsArchitecture
    $target = Get-WindowsReleaseTarget $architecture
    $paths = Get-InstallationPaths $env:LOCALAPPDATA
    Assert-NoConflictingCommand $paths.Executable

    $release = Get-LatestStableRelease
    $candidateAsset = Get-ReleaseAsset $release $target.AssetName
    $manifestAsset = Get-ReleaseAsset $release "SHA256SUMS"
    $temporaryDirectory = Join-Path ([IO.Path]::GetTempPath()) "yaatv-install-$([guid]::NewGuid().ToString('N'))"
    try {
        [void][IO.Directory]::CreateDirectory($temporaryDirectory)
        Assert-SufficientDiskSpace $paths.Directory $temporaryDirectory $candidateAsset.Size

        $manifestPath = Join-Path $temporaryDirectory "SHA256SUMS"
        [void](Invoke-OfficialDownload `
            -Url $manifestAsset.Url `
            -Destination $manifestPath `
            -AllowedHosts @("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com") `
            -Description "SHA256SUMS release manifest")
        $signatureVerified = Test-ReleaseSignature $release $manifestPath $temporaryDirectory
        $expectedDigest = Get-ManifestDigest $manifestPath $candidateAsset.Name

        $candidatePath = Join-Path $temporaryDirectory $candidateAsset.Name
        $downloadedFile = Invoke-OfficialDownload `
            -Url $candidateAsset.Url `
            -Destination $candidatePath `
            -AllowedHosts @("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com") `
            -Description $candidateAsset.Name
        if ($downloadedFile.Length -ne $candidateAsset.Size) {
            throw "The downloaded '$($candidateAsset.Name)' has an unexpected size. The release may be incomplete; no files were installed."
        }
        $actualDigest = (Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualDigest -cne $expectedDigest) {
            throw "The SHA-256 checksum for '$($candidateAsset.Name)' does not match SHA256SUMS. No files were installed."
        }
        Write-Host "SHA-256 checksum matched SHA256SUMS."

        $candidateVersion = Get-ExecutableVersion $candidatePath
        if ($candidateVersion -ne $release.Version) {
            throw "The downloaded executable reports version $candidateVersion, but release $($release.Tag) is $($release.Version). No files were installed."
        }

        if (Test-Path -LiteralPath $paths.Directory) {
            $directoryItem = Get-Item -LiteralPath $paths.Directory -Force
            if (($directoryItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "The managed install directory '$($paths.Directory)' is a reparse point. No files were installed."
            }
        }
        if (Test-Path -LiteralPath $paths.Executable) {
            $executableItem = Get-Item -LiteralPath $paths.Executable -Force
            if (($executableItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "The managed executable '$($paths.Executable)' is a reparse point. No files were installed."
            }
            $installedVersion = Get-ExecutableVersion $paths.Executable
            if ($installedVersion -gt $release.Version) {
                throw "The managed installation is newer (yaatv $installedVersion) than the latest stable release (yaatv $($release.Version)). The installer will not downgrade it."
            }
        }

        if ($target.Packaging -cne "onefile") {
            throw "The release uses an unsupported Windows package format '$($target.Packaging)'. No files were installed."
        }
        Write-Host "Installing yaatv $($release.Version) for Windows $architecture..."
        Invoke-OneFileInstallation $candidatePath $paths.Executable

        $installedVersion = Get-ExecutableVersion $paths.Executable
        if ($installedVersion -ne $release.Version) {
            throw "The installed executable reports version $installedVersion; expected $($release.Version). Binary verification failed."
        }

        $machinePath = [Environment]::GetEnvironmentVariable("Path", [EnvironmentVariableTarget]::Machine)
        $userPath = [Environment]::GetEnvironmentVariable("Path", [EnvironmentVariableTarget]::User)
        $verificationPath = Get-FreshWindowsPath $machinePath $userPath $paths.Directory
        Assert-FreshPathCommand $paths.Executable $release.Version $verificationPath

        if ($signatureVerified) {
            Write-Host "Installed yaatv $($release.Version) to $($paths.Executable)."
            Write-Host "Verification passed: the installed executable and a fresh PATH command both report yaatv $($release.Version)."
        }
        else {
            Write-Host "Installed yaatv $($release.Version) to $($paths.Executable)."
            Write-Host "Verification passed: the installed executable and a fresh PATH command both report yaatv $($release.Version)."
            Write-Host "The PGP signature was not verified because GPG is unavailable. See SECURITY.md for manual verification instructions."
        }
        Write-Host "Open a new terminal if your current terminal does not recognize yaatv."
    }
    finally {
        if (Test-Path -LiteralPath $temporaryDirectory) {
            try {
                Remove-Item -LiteralPath $temporaryDirectory -Recurse -Force -ErrorAction Stop
            }
            catch {
                Write-Warning "Could not remove the temporary installer directory '$temporaryDirectory': $($_.Exception.Message)"
            }
        }
    }
}

if ($RunInstaller) {
    try {
        Invoke-YaAtvInstaller
        $global:LASTEXITCODE = 0
    }
    catch {
        [Console]::Error.WriteLine("error: $($_.Exception.Message)")
        $global:LASTEXITCODE = 1
    }
}
}

if ($installerWasDotSourced) {
    . $installerImplementation $false
}
else {
    & $installerImplementation $true
}
Remove-Variable installerImplementation, installerWasDotSourced -ErrorAction SilentlyContinue
