[CmdletBinding()]
param(
    [string]$DataRoot = 'G:\us-intraday-lab',
    [string]$AvailableThrough = '2026-08-12',
    [int]$MaximumAttempts = 12
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$acquisitionScript = Join-Path $PSScriptRoot 'acquire_alpaca_iex_history.py'
$credentialDirectory = Join-Path $env:LOCALAPPDATA 'us-intraday-lab'
$credentialPath = Join-Path $credentialDirectory 'alpaca-paper-credential.xml'

function Read-SecretText {
    param([Parameter(Mandatory)][string]$Prompt)

    $secureValue = Read-Host -Prompt $Prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

if (Test-Path -LiteralPath $credentialPath) {
    $cachedCredential = Import-Clixml -LiteralPath $credentialPath
    $apiKey = $cachedCredential.UserName
    $secretKey = $cachedCredential.GetNetworkCredential().Password
    Write-Host 'Loaded the Windows-encrypted temporary credential cache.'
}
else {
    $apiKey = Read-SecretText -Prompt 'Alpaca Paper API Key ID (input hidden)'
    $secretKey = Read-SecretText -Prompt 'Alpaca Paper Secret Key (input hidden)'
    if ([string]::IsNullOrWhiteSpace($apiKey) -or [string]::IsNullOrWhiteSpace($secretKey)) {
        throw 'Both Alpaca Paper credential values are required.'
    }
    New-Item -ItemType Directory -Path $credentialDirectory -Force | Out-Null
    $encryptedSecret = ConvertTo-SecureString $secretKey -AsPlainText -Force
    $temporaryCredential = New-Object System.Management.Automation.PSCredential(
        $apiKey,
        $encryptedSecret
    )
    $temporaryCredential | Export-Clixml -LiteralPath $credentialPath -Force
    $temporaryCredential = $null
    $encryptedSecret = $null
    Write-Host 'Saved a Windows-DPAPI-encrypted temporary credential cache.'
}

if ([string]::IsNullOrWhiteSpace($apiKey) -or [string]::IsNullOrWhiteSpace($secretKey)) {
    throw 'Both Alpaca Paper credential values are required.'
}

try {
    $env:ALPACA_PAPER_API_KEY = $apiKey
    $env:ALPACA_PAPER_SECRET_KEY = $secretKey
    $env:PYTHONPATH = Join-Path $repoRoot 'src'
    $apiKey = $null
    $secretKey = $null

    $logDirectory = Join-Path $DataRoot 'data\staging\alpaca_iex_1min'
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $runStamp = Get-Date -Format 'yyyyMMdd-HHmmss'

    Write-Host 'Credentials loaded into this download process; values were not displayed.'
    for ($attempt = 1; $attempt -le $MaximumAttempts; $attempt++) {
        $logPath = Join-Path $logDirectory ("acquisition-$runStamp-attempt-$attempt-out.log")
        $errorLogPath = Join-Path $logDirectory (
            "acquisition-$runStamp-attempt-$attempt-err.log"
        )
        Write-Host "Starting read-only Alpaca IEX acquisition (attempt $attempt/$MaximumAttempts)..."
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            # Windows PowerShell wraps any native stderr as NativeCommandError when
            # ErrorActionPreference is Stop. Let Python finish, then inspect its real exit code.
            $ErrorActionPreference = 'Continue'
            & python $acquisitionScript `
                --root $DataRoot `
                --available-through $AvailableThrough 1>> $logPath 2>> $errorLogPath
            $acquisitionExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        if ($acquisitionExitCode -eq 0) {
            Remove-Item -LiteralPath $credentialPath -Force -ErrorAction SilentlyContinue
            Write-Host 'Acquisition completed successfully.'
            exit 0
        }
        if ($attempt -eq $MaximumAttempts) {
            throw "Acquisition did not complete after $MaximumAttempts attempts. See $logPath"
        }
        $delaySeconds = [Math]::Min(300, 30 * $attempt)
        Write-Host "Acquisition exited with code $acquisitionExitCode; retrying in $delaySeconds seconds."
        Start-Sleep -Seconds $delaySeconds
    }
}
finally {
    Remove-Item Env:ALPACA_PAPER_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:ALPACA_PAPER_SECRET_KEY -ErrorAction SilentlyContinue
    $apiKey = $null
    $secretKey = $null
}
