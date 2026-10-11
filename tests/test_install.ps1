$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "..\install.ps1")

function Assert-Equal {
    param(
        [Parameter(Mandatory = $true)][object]$Actual,
        [Parameter(Mandatory = $true)][object]$Expected,
        [Parameter(Mandatory = $true)][string]$Name
    )
    if ($Actual -cne $Expected) {
        throw "$Name failed: expected '$Expected', received '$Actual'."
    }
}

function Assert-Throws {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Action,
        [Parameter(Mandatory = $true)][string]$ExpectedMessage
    )
    $didThrow = $false
    try {
        & $Action | Out-Null
    }
    catch {
        $didThrow = $true
        if ($_.Exception.Message -notlike "*$ExpectedMessage*") {
            throw "Expected an error containing '$ExpectedMessage', received '$($_.Exception.Message)'."
        }
    }
    if (-not $didThrow) {
        throw "Expected an error containing '$ExpectedMessage', but no error was raised."
    }
}

Assert-Equal (ConvertTo-NormalizedArchitecture "AMD64") "x64" "AMD64 normalization"
Assert-Equal (ConvertTo-NormalizedArchitecture "x86_64") "x64" "x86_64 normalization"
Assert-Equal (ConvertTo-NormalizedArchitecture "ARM64") "arm64" "ARM64 normalization"
Assert-Equal (ConvertTo-NormalizedArchitecture "i686") "x86" "x86 normalization"
Assert-Equal (Get-WindowsReleaseTarget "AMD64").AssetName "yaatv-windows-x64.exe" "Windows x64 asset mapping"
Assert-Throws { Get-WindowsReleaseTarget "ARM64" } "not supported"
Assert-Throws { Get-WindowsReleaseTarget "x86" } "not supported"

Assert-Equal (ConvertTo-StableVersion "v0.7.0") ([version]"0.7.0") "release version parsing"
Assert-Throws { ConvertTo-StableVersion "v0.7.0-rc.1" } "not a stable"
Assert-Throws { ConvertTo-StableVersion "v00.7.0" } "not a stable"

$assetName = "yaatv-windows-x64.exe"
$assetUrl = "https://github.com/yaatv/yaatv/releases/download/v1.2.3/$assetName"
$validMetadata = [pscustomobject]@{
    tag_name = "v1.2.3"
    draft = $false
    prerelease = $false
    assets = @(
        [pscustomobject]@{
            name = "yaatv-windows-x64.zip"
            size = [long]200
            browser_download_url = "https://github.com/yaatv/yaatv/releases/download/v1.2.3/yaatv-windows-x64.zip"
        },
        [pscustomobject]@{
            name = $assetName
            size = [long]100
            browser_download_url = $assetUrl
        }
    )
}
$release = Assert-LatestStableRelease $validMetadata
$selectedAsset = Get-ReleaseAsset $release $assetName
Assert-Equal $selectedAsset.Name $assetName "exact release asset selection"
Assert-Equal $selectedAsset.Size ([long]100) "release asset size"
Assert-Throws { Get-ReleaseAsset $release "yaatv-windows-arm64.exe" } "does not contain"

$duplicateMetadata = [pscustomobject]@{
    Tag = "v1.2.3"
    Assets = @(
        [pscustomobject]@{ name = $assetName; size = [long]100; browser_download_url = $assetUrl },
        [pscustomobject]@{ name = $assetName; size = [long]100; browser_download_url = $assetUrl }
    )
}
Assert-Throws { Get-ReleaseAsset $duplicateMetadata $assetName } "multiple assets"
Assert-Throws {
    Assert-LatestStableRelease ([pscustomobject]@{
        tag_name = "v1.2.3"
        draft = $false
        prerelease = $true
        assets = @()
    })
} "prerelease"
Assert-Throws {
    Assert-LatestStableRelease ([pscustomobject]@{
        tag_name = "v1.2.3"
        draft = $true
        prerelease = $false
        assets = @()
    })
} "draft"
Assert-Throws {
    Assert-LatestStableRelease ([pscustomobject]@{
        tag_name = "v1.2.3"
        assets = @()
    })
} "malformed release metadata"
Assert-Throws {
    Assert-LatestStableRelease ([pscustomobject]@{
        tag_name = "v1.2.3"
        draft = $false
        assets = @()
    })
} "malformed release metadata"
Assert-Throws {
    Assert-LatestStableRelease ([pscustomobject]@{
        tag_name = "v1.2.3"
        draft = $false
        prerelease = $false
    })
} "malformed release metadata"
Assert-Throws {
    Get-ReleaseAsset ([pscustomobject]@{
        Tag = "v1.2.3"
        Assets = @([pscustomobject]@{ name = $assetName })
    }) $assetName
} "incomplete or invalid"

Assert-Throws {
    Assert-OfficialReleaseAssetUrl "https://example.com/yaatv.exe" "v1.2.3" $assetName
} "official yaatv release assets"
Assert-Throws {
    Assert-OfficialReleaseAssetUrl "http://github.com/yaatv/yaatv/releases/download/v1.2.3/$assetName" "v1.2.3" $assetName
} "official yaatv release assets"

$trustedFingerprint = "89687756391589496E71E6665314FF77F9EE3C59"
$trustedKeyOutput = @(
    "pub:u:4096:1:5314FF77F9EE3C59:1:1:::::scESC:",
    "fpr:::::::::${trustedFingerprint}:"
)
$trustedImportOutput = @("[GNUPG:] IMPORT_OK 1 $trustedFingerprint")
$trustedSignatureOutput = @(
    "[GNUPG:] VALIDSIG $trustedFingerprint 2026-10-10 1791590400 0 4 0 1 10 00 $trustedFingerprint"
)
Assert-TrustedReleaseSignature $trustedKeyOutput $trustedImportOutput $trustedSignatureOutput
Assert-Throws {
    Assert-TrustedReleaseSignature `
        ($trustedKeyOutput + @("pub:u:4096:1:BAD:1:1:::::scESC:", "fpr:::::::::AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:")) `
        $trustedImportOutput `
        $trustedSignatureOutput
} "exactly the trusted YAATV primary key"
Assert-Throws {
    Assert-TrustedReleaseSignature `
        $trustedKeyOutput `
        @("[GNUPG:] IMPORT_OK 1 AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA") `
        $trustedSignatureOutput
} "did not import the trusted YAATV release key"
Assert-Throws {
    Assert-TrustedReleaseSignature `
        $trustedKeyOutput `
        @() `
        $trustedSignatureOutput
} "did not import exactly one YAATV release key"
Assert-Throws {
    Assert-TrustedReleaseSignature `
        $trustedKeyOutput `
        $trustedImportOutput `
        @("[GNUPG:] VALIDSIG AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA 2026-10-10 1791590400 0 4 0 1 10 00 BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB")
} "not made by the trusted YAATV release key"
Assert-Throws {
    Assert-TrustedReleaseSignature `
        $trustedKeyOutput `
        $trustedImportOutput `
        ($trustedSignatureOutput + $trustedSignatureOutput)
} "exactly one valid SHA256SUMS signature"
foreach ($invalidSignatureStatus in @("EXPSIG", "EXPKEYSIG", "REVKEYSIG", "KEYREVOKED", "BADSIG", "ERRSIG", "SIGEXPIRED")) {
    Assert-Throws {
        Assert-TrustedReleaseSignature `
            $trustedKeyOutput `
            $trustedImportOutput `
            (@("[GNUPG:] $invalidSignatureStatus $trustedFingerprint") + $trustedSignatureOutput)
    } "invalid, expired, or revoked"
}

$gpgCommand = Get-Command gpg -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -ne $gpgCommand) {
    $previousErrorActionPreference = $ErrorActionPreference
    $previousLastExitCodeVariable = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
    $previousLastExitCode = 0
    if ($null -ne $previousLastExitCodeVariable -and $null -ne $previousLastExitCodeVariable.Value) {
        $previousLastExitCode = [int]$previousLastExitCodeVariable.Value
    }
    try {
        $ErrorActionPreference = "Stop"
        $global:LASTEXITCODE = 23
        $gpgResult = Invoke-OpenPgpProcess $gpgCommand.Path @("--batch", "--no-options", "--installer-test-invalid-option")
        Assert-Equal ($gpgResult.ExitCode -ne 0) $true "GPG invalid-option exit code"
        Assert-Equal ($gpgResult.Output.Count -gt 0) $true "GPG stderr captured without terminating"
        Assert-Equal $ErrorActionPreference "Stop" "GPG error preference restored"
        Assert-Equal $global:LASTEXITCODE 23 "GPG last exit code restored"
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        $global:LASTEXITCODE = $previousLastExitCode
    }
}

$temporaryDirectory = Join-Path ([IO.Path]::GetTempPath()) "yaatv-installer-test-$([guid]::NewGuid().ToString('N'))"
[void][IO.Directory]::CreateDirectory($temporaryDirectory)
try {
    $manifestPath = Join-Path $temporaryDirectory "SHA256SUMS"
    $digest = "a" * 64
    [IO.File]::WriteAllText(
        $manifestPath,
        "$digest  $assetName`n$(("b" * 64))  yaatv-linux-x64.zip`n",
        [Text.Encoding]::UTF8
    )
    Assert-Equal (Get-ManifestDigest $manifestPath $assetName) $digest "manifest digest selection"

    [IO.File]::WriteAllText($manifestPath, "$digest  $assetName`n$digest  $assetName`n", [Text.Encoding]::UTF8)
    Assert-Throws { Get-ManifestDigest $manifestPath $assetName } "multiple entries"

    [IO.File]::WriteAllText($manifestPath, "not a checksum`n", [Text.Encoding]::UTF8)
    Assert-Throws { Get-ManifestDigest $manifestPath $assetName } "malformed entry"
}
finally {
    Remove-Item -LiteralPath $temporaryDirectory -Recurse -Force
}

$installDirectory = "C:\Users\Example\AppData\Local\Programs\yaatv\bin"
$equivalentEntry = '"c:/users/example/appdata/local/programs/yaatv/bin/"'
Assert-Equal (Test-PathContainsEntry $equivalentEntry $installDirectory) $true "case and trailing slash PATH comparison"
Assert-Equal (Get-FreshWindowsPath "C:\Windows" $installDirectory $installDirectory) "C:\Windows;$installDirectory" "fresh PATH construction from persisted user PATH"
Assert-Throws { Get-FreshWindowsPath "C:\Windows" "C:\Other" $installDirectory } "persisted current-user PATH"

$paths = Get-InstallationPaths "C:\Users\Example\AppData\Local"
Assert-Equal $paths.Directory "C:\Users\Example\AppData\Local\Programs\yaatv\bin" "managed install directory"
Assert-Equal $paths.Executable "C:\Users\Example\AppData\Local\Programs\yaatv\bin\yaatv.exe" "managed executable path"
Assert-Throws { Get-InstallationPaths "relative\localappdata" } "absolute path"
Assert-Throws { Get-InstallationPaths "C:\Users\Example;C:\Other" } "absolute path"
Assert-Throws { Get-InstallationPaths "C:relative\AppData\Local" } "fully qualified absolute path"
Assert-Throws { Get-InstallationPaths "\Users\Example\AppData\Local" } "fully qualified absolute path"
Assert-Throws { Get-InstallationPaths "C:\" } "inside a user profile"

$downloadTestDirectory = Join-Path ([IO.Path]::GetTempPath()) "yaatv-download-test-$([guid]::NewGuid().ToString('N'))"
[void][IO.Directory]::CreateDirectory($downloadTestDirectory)
try {
    function Invoke-WebRequest {
        [CmdletBinding()]
        param(
            [string]$Uri,
            [string]$Method,
            [string]$OutFile,
            [switch]$PassThru,
            [switch]$UseBasicParsing,
            [int]$MaximumRedirection,
            [int]$TimeoutSec
        )
        if (-not $PassThru) {
            throw "The installer did not request the download response."
        }
        [IO.File]::WriteAllText($OutFile, "test download")
        return [pscustomobject]@{
            BaseResponse = [pscustomobject]@{ ResponseUri = $script:MockDownloadResponseUri }
        }
    }

    $downloadPath = Join-Path $downloadTestDirectory "asset.bin"
    $script:MockDownloadResponseUri = [uri]"https://release-assets.githubusercontent.com/asset.bin"
    $download = Invoke-OfficialDownload `
        -Url "https://github.com/yaatv/yaatv/releases/download/v1.2.3/asset.bin" `
        -Destination $downloadPath `
        -AllowedHosts @("release-assets.githubusercontent.com") `
        -Description "test asset"
    Assert-Equal $download.Length ([long]13) "download response body saved"

    $script:MockDownloadResponseUri = [uri]"https://downloads.example.com/asset.bin"
    Assert-Throws {
        Invoke-OfficialDownload `
            -Url "https://github.com/yaatv/yaatv/releases/download/v1.2.3/asset.bin" `
            -Destination $downloadPath `
            -AllowedHosts @("release-assets.githubusercontent.com") `
            -Description "test asset"
    } "outside the approved HTTPS GitHub hosts"
}
finally {
    Remove-Item Function:\Invoke-WebRequest -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $downloadTestDirectory -Recurse -Force
}

Write-Host "PowerShell installer tests passed."
