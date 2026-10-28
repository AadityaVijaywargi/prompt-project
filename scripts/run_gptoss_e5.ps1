# run_gptoss_e5.ps1 [-Variant bias_aware]
# E5 on gpt-oss-120b (60-item subset, 920 calls per variant) on one Groq key.
# Runs whatever is still missing, commits only this variant's logs plus cache files, pushes,
# and waits 30 min between rounds when the Groq daily limit is hit. Stops when no call is left.
#   powershell -File scripts\run_gptoss_e5.ps1 -Variant bias_aware
# The key is read from the GROQ_API_KEY user environment variable and never printed.
param([ValidateSet("bias_aware", "hindi_rubric")][string]$Variant = "bias_aware")

Set-Location (Split-Path -Parent $PSScriptRoot)
$env:PYTHONUTF8 = "1"; $env:PYTHONUNBUFFERED = "1"
if (-not $env:GROQ_API_KEY) {
  $env:GROQ_API_KEY = [Environment]::GetEnvironmentVariable('GROQ_API_KEY', 'User')
}
if (-not $env:GROQ_API_KEY) { "GROQ_API_KEY is not set (user environment variable)"; exit 2 }

$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
# Uncached calls left; unlike a dry run of the runner, this writes no log file when the count is 0.
$left = @"
from lb.config import experiments_config
from lb.runners.e5_mitigation import subset_for, plan
from lb.runners.common import build_judges
from lb.budget import summarize
cfg = experiments_config()
t, c = summarize(plan(subset_for(cfg), ['gpt-oss-120b'], cfg, '$Variant'), build_judges(['gpt-oss-120b'], offline=True))
print(sum(t.values()) - sum(c.values()))
"@
function Calls-Left { [int](& $py -c $left) }
for ($round = 1; $round -le 30; $round++) {
  "=== E5 $Variant round $round started $(Get-Date -Format s)"
  git pull -q --rebase
  if ((Calls-Left) -eq 0) { break }
  & $py -m lb.runners.e5_mitigation --variant $Variant --judges gpt-oss-120b --yes
  git add "results/raw/e*__${Variant}-*.jsonl" results/cache
  git commit -q -m "gpt-oss E5 $Variant"
  git pull -q --rebase; git push -q
  if ($LASTEXITCODE -eq 0) { "push ok" } else { "PUSH FAILED: check git status (a stuck rebase?)" }
  $n = Calls-Left
  "round ${round}: $n calls left"
  if ($n -eq 0) { break }
  "waiting 30 min for the Groq limit to refill"
  Start-Sleep -Seconds 1800
}
"=== E5 $Variant loop ended $(Get-Date -Format s), calls left: $(Calls-Left)"
