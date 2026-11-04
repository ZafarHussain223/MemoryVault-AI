param(
 [ValidateSet('api','web','test','e2e','install','reindex','ai')][string]$Mode='web',
 [string]$PythonExe='python'
)
$ErrorActionPreference='Stop'
$projectRoot=$PSScriptRoot
$env:TEMP=Join-Path $projectRoot 'work/tmp'
$env:TMP=$env:TEMP
$env:NEXT_SWC_PATH=Join-Path $projectRoot 'work/next-swc'
$env:NEXT_TELEMETRY_DISABLED='1'
$env:HF_HOME=Join-Path $projectRoot 'work/models'
if(-not $env:MV_PYTHON_PACKAGES){$env:MV_PYTHON_PACKAGES=Join-Path $projectRoot 'work/python-packages'}
$env:PYTHONPATH=$env:MV_PYTHON_PACKAGES
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
# Read local configuration as data; never execute shell text from an env file.
$localConfig=Join-Path $projectRoot '.env.local'
if(Test-Path -LiteralPath $localConfig){
 foreach($configLine in Get-Content -LiteralPath $localConfig){
  if($configLine -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$'){
   $configName=$Matches[1]; $configValue=$Matches[2].Trim()
   if(($configValue.StartsWith('"') -and $configValue.EndsWith('"')) -or ($configValue.StartsWith("'") -and $configValue.EndsWith("'"))){$configValue=$configValue.Substring(1,$configValue.Length-2)}
   [Environment]::SetEnvironmentVariable($configName,$configValue,'Process')
  }
 }
}
switch($Mode){
 'ai' { & (Join-Path $projectRoot 'local-ai.ps1') serve }
 'install' {
  Set-Location $projectRoot
  & $PythonExe -m pip install --target $env:PYTHONPATH --cache-dir work/pip-cache -r services/api/requirements-core.txt
  if($LASTEXITCODE -ne 0){throw 'Python dependency installation failed'}
  Set-Location (Join-Path $projectRoot 'apps/web')
  npm.cmd ci --cache (Join-Path $projectRoot 'work/npm-cache')
  if($LASTEXITCODE -ne 0){throw 'Frontend dependency installation failed'}
 }
 'api' {
  Set-Location (Join-Path $projectRoot 'services/api')
  & $PythonExe -m alembic upgrade head
  if($LASTEXITCODE -ne 0){throw 'Database migration failed'}
  & $PythonExe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
 }
 'web' {
  Set-Location (Join-Path $projectRoot 'apps/web')
  npm.cmd run dev
 }
 'test' {
  Set-Location (Join-Path $projectRoot 'services/api')
  & $PythonExe -m pytest -q
  if($LASTEXITCODE -ne 0){throw 'API tests failed'}
  Set-Location (Join-Path $projectRoot 'apps/web')
  npm.cmd run typecheck
  if($LASTEXITCODE -ne 0){throw 'Type checking failed'}
  npm.cmd run build
  if($LASTEXITCODE -ne 0){throw 'Production build failed'}
 }
 'e2e' {
  Set-Location $projectRoot
  & $PythonExe scripts/run_browser_tests.py
  if($LASTEXITCODE -ne 0){throw 'Browser checks failed; see apps/web/test-results'}
 }
 'reindex' {
  Set-Location (Join-Path $projectRoot 'services/api')
  & $PythonExe -m app.maintenance reindex
  if($LASTEXITCODE -ne 0){throw 'Reindex failed'}
 }
}
