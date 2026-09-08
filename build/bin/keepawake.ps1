# keepawake.ps1 -- run a command while holding Windows awake (the equivalent of macOS `caffeinate -i`).
#   powershell -NoProfile -ExecutionPolicy Bypass -File keepawake.ps1 [-Display] [--] <command> [args...]
# Holds ES_SYSTEM_REQUIRED (no idle sleep) for as long as the child runs; -Display adds ES_DISPLAY_REQUIRED
# (no screen sleep either). The state is cleared when the child exits, and the child's exit code is returned.
# Ctrl+C reaches the child too. No param() block on purpose: PowerShell's parameter binder would otherwise try
# to interpret the child's own --flags, so everything is read from $args by hand.
$ErrorActionPreference = 'Continue'
$argv = @($args)
$display = $false
if ($argv.Length -gt 0 -and $argv[0] -eq '-Display') { $display = $true; $argv = @($argv | Select-Object -Skip 1) }
if ($argv.Length -gt 0 -and $argv[0] -eq '--') { $argv = @($argv | Select-Object -Skip 1) }
if ($argv.Length -eq 0) { [Console]::Error.WriteLine('keepawake.ps1: no command given'); exit 2 }

Add-Type -Namespace KeepAwake -Name Native -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)]
public static extern uint SetThreadExecutionState(uint esFlags);
'@
# hex literals are signed Int32 in Windows PowerShell 5.1, so the top bit is spelled out in decimal
$ES_CONTINUOUS = [uint32]2147483648
$ES_SYSTEM_REQUIRED = [uint32]1
$ES_DISPLAY_REQUIRED = [uint32]2
$flags = $ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED
if ($display) { $flags = $flags -bor $ES_DISPLAY_REQUIRED }

$prev = [KeepAwake.Native]::SetThreadExecutionState($flags)
if ($prev -eq 0) { [Console]::Error.WriteLine('keepawake.ps1: SetThreadExecutionState failed; running without the keep-awake') }
$code = 1
try {
  $exe = $argv[0]
  $rest = @()
  if ($argv.Length -gt 1) { $rest = @($argv | Select-Object -Skip 1) }
  # the child inherits this console: stdin, stdout, stderr and Ctrl+C all pass straight through
  & $exe @rest
  $code = $LASTEXITCODE
  if ($null -eq $code) { $code = 0 }
} finally {
  [void][KeepAwake.Native]::SetThreadExecutionState($ES_CONTINUOUS)
}
exit $code
