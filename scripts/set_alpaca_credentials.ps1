[CmdletBinding()]
param(
    [switch]$Remove,
    [switch]$Gui
)

$ErrorActionPreference = 'Stop'
$credentialDirectory = Join-Path $env:LOCALAPPDATA 'us-intraday-lab'
$credentialPath = Join-Path $credentialDirectory 'alpaca-paper-credential.xml'

if ($Remove) {
    Remove-Item -LiteralPath $credentialPath -Force -ErrorAction SilentlyContinue
    Write-Host 'Temporary Alpaca credential cache removed.'
    exit 0
}

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

if ($Gui) {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'Set temporary Alpaca Paper credentials'
    $form.Size = New-Object System.Drawing.Size(560, 260)
    $form.StartPosition = 'CenterScreen'
    $form.TopMost = $true

    $keyBox = New-Object System.Windows.Forms.TextBox
    $keyBox.Location = New-Object System.Drawing.Point(20, 50)
    $keyBox.Size = New-Object System.Drawing.Size(500, 25)
    $form.Controls.Add($keyBox)
    $keyLabel = New-Object System.Windows.Forms.Label
    $keyLabel.Text = 'API Key ID'
    $keyLabel.Location = New-Object System.Drawing.Point(20, 25)
    $keyLabel.AutoSize = $true
    $form.Controls.Add($keyLabel)

    $secretBox = New-Object System.Windows.Forms.TextBox
    $secretBox.Location = New-Object System.Drawing.Point(20, 115)
    $secretBox.Size = New-Object System.Drawing.Size(500, 25)
    $secretBox.UseSystemPasswordChar = $true
    $form.Controls.Add($secretBox)
    $secretLabel = New-Object System.Windows.Forms.Label
    $secretLabel.Text = 'Secret Key'
    $secretLabel.Location = New-Object System.Drawing.Point(20, 90)
    $secretLabel.AutoSize = $true
    $form.Controls.Add($secretLabel)

    $saveButton = New-Object System.Windows.Forms.Button
    $saveButton.Text = 'Encrypt for one download'
    $saveButton.Location = New-Object System.Drawing.Point(180, 165)
    $saveButton.Size = New-Object System.Drawing.Size(200, 35)
    $form.Controls.Add($saveButton)
    $form.AcceptButton = $saveButton
    $script:saved = $false
    $saveButton.Add_Click({
        $script:apiKey = $keyBox.Text.Trim()
        $script:secretKey = $secretBox.Text.Trim()
        if (-not [string]::IsNullOrWhiteSpace($script:apiKey) -and
            -not [string]::IsNullOrWhiteSpace($script:secretKey)) {
            $script:saved = $true
            $keyBox.Clear()
            $secretBox.Clear()
            $form.Close()
        }
    })
    $form.Add_Shown({ $keyBox.Focus() })
    $form.ShowDialog() | Out-Null
    if (-not $script:saved) {
        throw 'Credential entry was closed before both values were supplied.'
    }
}
else {
    $apiKey = Read-SecretText -Prompt 'Alpaca Paper API Key ID (input hidden)'
    $secretKey = Read-SecretText -Prompt 'Alpaca Paper Secret Key (input hidden)'
}

if ([string]::IsNullOrWhiteSpace($apiKey) -or [string]::IsNullOrWhiteSpace($secretKey)) {
    throw 'Both Alpaca Paper credential values are required.'
}

New-Item -ItemType Directory -Path $credentialDirectory -Force | Out-Null
$encryptedSecret = ConvertTo-SecureString $secretKey -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential($apiKey, $encryptedSecret)
$credential | Export-Clixml -LiteralPath $credentialPath -Force
$apiKey = $null
$secretKey = $null
$encryptedSecret = $null
$credential = $null

Write-Host 'Saved a Windows-DPAPI-encrypted temporary credential cache.'
Write-Host 'It is readable only by this Windows user and is deleted after a successful download.'
