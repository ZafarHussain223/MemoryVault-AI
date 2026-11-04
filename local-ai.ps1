param([ValidateSet('serve','status','unload','warmup','verify')][string]$Mode='serve')
$ErrorActionPreference='Stop'
$projectRoot=$PSScriptRoot
$runtime=Join-Path $projectRoot 'work/ai-runtime/ollama-0.40.12/ollama.exe'
if(-not (Test-Path -LiteralPath $runtime)){throw 'The local Ollama runtime is missing. See the Optional local AI section in README.md.'}
$env:OLLAMA_HOST='127.0.0.1:11434'
$env:OLLAMA_MODELS=Join-Path $projectRoot 'work/models/ollama'
$env:OLLAMA_NO_CLOUD='1'
$env:OLLAMA_NUM_PARALLEL='1'
$env:OLLAMA_MAX_LOADED_MODELS='2'
$env:OLLAMA_MAX_QUEUE='4'
$env:OLLAMA_CONTEXT_LENGTH='4096'
$env:OLLAMA_FLASH_ATTENTION='1'
$env:OLLAMA_KV_CACHE_TYPE='q8_0'
$env:OLLAMA_KEEP_ALIVE='5m'
$env:CUDA_CACHE_PATH=Join-Path $projectRoot 'work/tmp/cuda-cache'
$env:CUDA_CACHE_MAXSIZE='1073741824'
$env:TEMP=Join-Path $projectRoot 'work/tmp'
$env:TMP=$env:TEMP
$env:PYTHONPATH=Join-Path $projectRoot 'work/python-packages'
New-Item -ItemType Directory -Force -Path $env:CUDA_CACHE_PATH | Out-Null
switch($Mode){
 'serve' { Write-Host 'Starting local-only AI. Keep this terminal open; press Ctrl+C to stop.'; & $runtime serve }
 'status' { & $runtime list; & $runtime ps }
 'unload' { & $runtime stop 'qwen3:4b-instruct-2507-q4_K_M'; & $runtime stop 'qwen3-embedding:0.6b' }
 'warmup' { & python (Join-Path $projectRoot 'scripts/warm_local_ai.py') }
 'verify' { & python (Join-Path $projectRoot 'scripts/verify_local_ai.py') }
}
if($LASTEXITCODE -ne 0){throw "Local AI command failed (exit $LASTEXITCODE)."}
