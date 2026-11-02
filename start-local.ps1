$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:Path = "$PSScriptRoot\.tools;C:\Program Files\Docker\Docker\resources\bin;" + $env:Path

# Убираем ранее запущенный этим проектом фоновый проброс порта.
if (Test-Path '.tools/port-forward.pid') {
    $forwardProcessId = [int](Get-Content '.tools/port-forward.pid')
    $forwardProcess = Get-Process -Id $forwardProcessId -ErrorAction SilentlyContinue
    if ($forwardProcess -and $forwardProcess.Path -eq "$PSScriptRoot\.tools\kubectl.exe") {
        $forwardProcess | Stop-Process
    }
}

function Check-Exit {
    if ($LASTEXITCODE -ne 0) { throw 'Команда завершилась с ошибкой' }
}

docker info --format '{{.ServerVersion}}'
Check-Exit
minikube start -p kasperskiy --driver=docker --cpus=6 --memory=12288 --kubernetes-version=v1.35.0
Check-Exit
docker build -t inference-cpu:0.27.0-3 .
Check-Exit
docker build -f Dockerfile.download -t model-download:1 .
Check-Exit
minikube -p kasperskiy image load inference-cpu:0.27.0-3 model-download:1 --daemon=true --overwrite=true
Check-Exit

if (!(Test-Path '.env')) {
    $tokenBytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($tokenBytes)
    $rng.Dispose()
    $newToken = [Convert]::ToBase64String($tokenBytes)
    [IO.File]::WriteAllText((Join-Path $PSScriptRoot '.env'), "API_TOKEN=$newToken`nHF_TOKEN=`n")
}
$settings = Get-Content '.env' -Raw | ConvertFrom-StringData
if (!$settings.API_TOKEN) { throw 'Задайте API_TOKEN в .env' }
$secret = @{
    apiVersion = 'v1'
    kind = 'Secret'
    metadata = @{ name = 'inference-secrets' }
    type = 'Opaque'
    stringData = @{ API_TOKEN = $settings.API_TOKEN; HF_TOKEN = [string]$settings.HF_TOKEN }
}
$secret | ConvertTo-Json -Depth 4 -Compress | kubectl --context kasperskiy apply -f -
Check-Exit
kubectl --context kasperskiy apply -k k8s
Check-Exit
kubectl --context kasperskiy rollout restart deployment/inference
Check-Exit
kubectl --context kasperskiy rollout status deployment/inference --timeout=1800s
Check-Exit
kubectl --context kasperskiy port-forward service/inference 8000:8000
