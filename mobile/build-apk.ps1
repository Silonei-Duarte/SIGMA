$ErrorActionPreference = "Stop"

$mobileRoot = $PSScriptRoot
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

if (-not (Test-Path -LiteralPath $javaExecutable)) {
    throw "JDK nao encontrado em $javaRoot"
}
if (-not (Test-Path -LiteralPath (Join-Path $sdkRoot "platforms\android-36"))) {
    throw "Android SDK 36 nao encontrado em $sdkRoot"
}
if (-not (Test-Path -LiteralPath $gradleWrapper)) {
    throw "Projeto Android nao encontrado. Execute: npx cap add android"
}

$env:JAVA_HOME = $javaRoot
$env:ANDROID_HOME = $sdkRoot
$env:ANDROID_SDK_ROOT = $sdkRoot

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
        & $gradleWrapper assembleDebug
        if ($LASTEXITCODE -ne 0) {
            throw "Falha ao gerar o APK."
        }
    } finally {
        Pop-Location
    }

    $sourceApk = Join-Path $mobileRoot "android\app\build\outputs\apk\debug\app-debug.apk"
    $distDir = Join-Path $mobileRoot "dist"
    $targetApk = Join-Path $distDir "SIGMA.apk"
    New-Item -ItemType Directory -Force -Path $distDir | Out-Null
    Copy-Item -LiteralPath $sourceApk -Destination $targetApk -Force
    Write-Output "APK gerado: $targetApk"
} finally {
    Pop-Location
}
