$port = 8000
$url = "http://localhost:$port"

# Check if port 8000 is already active
$isListening = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue

if (-not $isListening) {
    Write-Host "Starting IBVAP server..."
    Start-Process -FilePath "python" -ArgumentList "run_server.py" -WorkingDirectory "d:\IBVAP" -WindowStyle Minimized
    Start-Sleep -Seconds 2
}

# Open the website in default browser
Start-Process $url
