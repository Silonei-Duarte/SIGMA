$ErrorActionPreference = "Stop"

$mobileRoot = $PSScriptRoot
$projectEnvFile = Join-Path $mobileRoot "..\.env"
$sdkRoot = if ($env:ANDROID_SDK_ROOT) {
    $env:ANDROID_SDK_ROOT
} else {
    Join-Path $env:LOCALAPPDATA "Android\Sdk"
}
$javaRoot = if ($env:JAVA_HOME) {
    $env:JAVA_HOME
} else {
    "C:\Program Files\Android\Android Studio\jbr"
}
$javaExecutable = Join-Path $javaRoot "bin\java.exe"
$gradleWrapper = Join-Path $mobileRoot "android\gradlew.bat"
$keystoreFile = Join-Path $mobileRoot "keystore\sigma-release.jks"

if (-not (Test-Path -LiteralPath $javaExecutable)) {
    throw "JDK nao encontrado em $javaRoot"
}
if (-not (Test-Path -LiteralPath (Join-Path $sdkRoot "platforms\android-36"))) {
    throw "Android SDK 36 nao encontrado em $sdkRoot"
}
if (-not (Test-Path -LiteralPath $gradleWrapper)) {
    throw "Projeto Android nao encontrado. Execute: npx cap add android"
}
if (-not (Test-Path -LiteralPath $keystoreFile)) {
    throw "Keystore release nao encontrado em $keystoreFile"
}

$releasePassword = $env:SIGMA_KEYSTORE_PASSWORD
if (-not $releasePassword -and (Test-Path -LiteralPath $projectEnvFile)) {
    foreach ($line in Get-Content -LiteralPath $projectEnvFile -Encoding UTF8) {
        if ($line.StartsWith("SIGMA_KEYSTORE_PASSWORD=")) {
            $releasePassword = $line.Substring("SIGMA_KEYSTORE_PASSWORD=".Length)
            break
        }
    }
}
if (-not $releasePassword) {
    throw "Defina SIGMA_KEYSTORE_PASSWORD no arquivo .env do projeto."
}

$env:JAVA_HOME = $javaRoot
$env:ANDROID_HOME = $sdkRoot
$env:ANDROID_SDK_ROOT = $sdkRoot
$env:SIGMA_KEYSTORE_FILE = $keystoreFile
$env:SIGMA_KEYSTORE_PASSWORD = $releasePassword
$env:SIGMA_KEY_ALIAS = "sigma"
$env:SIGMA_KEY_PASSWORD = $releasePassword

$trustStore = Join-Path $env:LOCALAPPDATA "Android\sigma-gradle-cacerts"
if (Test-Path -LiteralPath $trustStore) {
    $trustOptions = "-Djavax.net.ssl.trustStore=$trustStore -Djavax.net.ssl.trustStorePassword=changeit"
    $env:GRADLE_OPTS = "$($env:GRADLE_OPTS) $trustOptions".Trim()
}

Push-Location $mobileRoot
try {
    & npx.cmd cap sync android
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao sincronizar o Capacitor."
    }

    Push-Location (Join-Path $mobileRoot "android")
    try {
        & $gradleWrapper assembleRelease
        if ($LASTEXITCODE -ne 0) {
            throw "Falha ao gerar o APK release."
        }
    } finally {
        Pop-Location
    }

    $sourceApk = Join-Path $mobileRoot "android\app\build\outputs\apk\release\app-release.apk"
    $distDir = Join-Path $mobileRoot "dist"
    $targetApk = Join-Path $distDir "SIGMA.apk"
    $artifactsDir = Join-Path $mobileRoot "..\artifacts"
    $downloadApk = Join-Path $artifactsDir "SIGMA.apk"
    New-Item -ItemType Directory -Force -Path $distDir | Out-Null
    New-Item -ItemType Directory -Force -Path $artifactsDir | Out-Null
    Copy-Item -LiteralPath $sourceApk -Destination $targetApk -Force
    Copy-Item -LiteralPath $sourceApk -Destination $downloadApk -Force
    Write-Output "APK release gerado: $targetApk"
    Write-Output "APK para download atualizado: $downloadApk"
} finally {
    $env:SIGMA_KEYSTORE_PASSWORD = $null
    $env:SIGMA_KEY_PASSWORD = $null
    $releasePassword = $null
    Pop-Location
}
