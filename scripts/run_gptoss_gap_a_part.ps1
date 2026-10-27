# run_gptoss_gap_a_part.ps1 -K <1-5>
# Gap A on gpt-oss-120b, split 5 ways (--shard K/5): run your own part on your own Groq key.
# Runs whatever is still missing for part K, commits only that part's log plus cache files, pushes,
# and waits 30 min between rounds if the Groq daily limit is hit. Stops when check_shard says COMPLETE.
#   powershell -File scripts\run_gptoss_gap_a_part.ps1 -K 2
# The key is read from the GROQ_API_KEY user environment variable and never printed.
param([Parameter(Mandatory = $true)][ValidateRange(1, 5)][int]$K)

Set-Location (Split-Path -Parent $PSScriptRoot)
$env:PYTHONUTF8 = "1"; $env:PYTHONUNBUFFERED = "1"
if (-not $env:GROQ_API_KEY) {
  $env:GROQ_API_KEY = [Environment]::GetEnvironmentVariable('GROQ_API_KEY', 'User')
}
if (-not $env:GROQ_API_KEY) { "GROQ_API_KEY is not set (user environment variable)"; exit 2 }

$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
$shard = "$K/5"
$check = @("scripts/check_shard.py", "--judge", "gpt-oss-120b", "--shard", $shard, "--experiments", "a_wrong")
for ($round = 1; $round -le 20; $round++) {
  "=== part $shard round $round started $(Get-Date -Format s)"
  git pull -q --rebase
  & $py @check
  if ($LASTEXITCODE -eq 0) { break }
  & $py -m lb.runners.a_wrong_pointwise --judges gpt-oss-120b --shard $shard --yes
  git add "results/raw/a_wrong__baseline-shard${K}of5-*.jsonl" results/cache
  git commit -q -m "gpt-oss gap A part $shard"
  git pull -q --rebase; git push -q
  if ($LASTEXITCODE -eq 0) { "push ok" } else { "PUSH FAILED: check git status (a stuck rebase?)" }
  & $py @check
  if ($LASTEXITCODE -eq 0) { break }
  "round $round done; waiting 30 min for the Groq limit to refill"
  Start-Sleep -Seconds 1800
}
"=== part $shard loop ended $(Get-Date -Format s)"
