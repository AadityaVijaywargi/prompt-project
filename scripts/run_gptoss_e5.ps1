# run_gptoss_e5.ps1 -K <1-3> [-Variant bias_aware]
# E5 on gpt-oss-120b (60-item subset, 920 calls per variant), split 3 ways (--shard K/3): run your own
# part on your own Groq key. Runs whatever is still missing for part K, commits only that part's logs plus
# cache files, pushes, and waits 30 min between rounds when the Groq daily limit is hit. Stops when no call
# of part K is left.
#   powershell -File scripts\run_gptoss_e5.ps1 -K 2
# The key is read from the GROQ_API_KEY user environment variable and never printed.
param([Parameter(Mandatory = $true)][ValidateRange(1, 3)][int]$K,
      [ValidateSet("bias_aware", "hindi_rubric")][string]$Variant = "bias_aware")

Set-Location (Split-Path -Parent $PSScriptRoot)
$env:PYTHONUTF8 = "1"; $env:PYTHONUNBUFFERED = "1"
if (-not $env:GROQ_API_KEY) {
  $env:GROQ_API_KEY = [Environment]::GetEnvironmentVariable('GROQ_API_KEY', 'User')
}
if (-not $env:GROQ_API_KEY) { "GROQ_API_KEY is not set (user environment variable)"; exit 2 }

$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
$shard = "$K/3"
# Uncached calls left in part K; unlike a dry run of the runner, this writes no log file when the count is 0.
function Calls-Left { [int](& $py scripts/e5_calls_left.py --variant $Variant --shard $shard) }
for ($round = 1; $round -le 30; $round++) {
  "=== E5 $Variant part $shard round $round started $(Get-Date -Format s)"
  git pull -q --rebase
  if ((Calls-Left) -eq 0) { break }
  & $py -m lb.runners.e5_mitigation --variant $Variant --judges gpt-oss-120b --shard $shard --yes
  git add "results/raw/e*__${Variant}-shard${K}of3-*.jsonl" results/cache
  git commit -q -m "gpt-oss E5 $Variant part $shard"
  git pull -q --rebase; git push -q
  if ($LASTEXITCODE -eq 0) { "push ok" } else { "PUSH FAILED: check git status (a stuck rebase?)" }
  $n = Calls-Left
  "round ${round}: $n calls left in part $shard"
  if ($n -eq 0) { break }
  "waiting 30 min for the Groq limit to refill"
  Start-Sleep -Seconds 1800
}
"=== E5 $Variant part $shard loop ended $(Get-Date -Format s), calls left: $(Calls-Left)"
