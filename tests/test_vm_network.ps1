$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../dsfst_network_common.ps1')
# Exercise address collision handling and the actual VBoxManage argument builder.
function Get-DsfstVMNames { @('template', 'clone') }
function Get-DsfstExtra([string]$Name, [string]$Key) { if ($Name -eq 'template') { '192.168.56.10' } else { '192.168.56.11' } }
if ((Get-DsfstAddress 'clone' '') -ne '192.168.56.11') { throw 'Existing address was not preserved.' }
$rejected = $false
try { Get-DsfstAddress 'clone' '192.168.56.10' | Out-Null } catch { $rejected = $true }
if (-not $rejected) { throw 'Duplicate address was accepted.' }
$rejected = $false
try { Get-DsfstAddress 'clone' '192.168.56.150' | Out-Null } catch { $rejected = $true }
if (-not $rejected) { throw 'DHCP pool address was accepted.' }
$script:networkCalls = @()
function Get-DsfstVMInfo { @{ VMState = 'poweroff'; nic2 = 'none'; macaddress2 = '080027123456' } }
function Invoke-DsfstVBox([string[]]$Arguments) { $script:networkCalls += ($Arguments -join '|'); [pscustomobject]@{ Lines=@(); ExitCode=0 } }
Set-DsfstVMNetwork 'clone' 'test adapter' '192.168.56.11'
if (-not ($script:networkCalls -contains 'guestproperty|set|clone|/DSFST/HostOnlyMAC|08:00:27:12:34:56|--flags|RDONLYGUEST')) { throw 'MAC property is incorrect.' }
if (-not ($script:networkCalls -contains 'guestproperty|set|clone|/DSFST/HostOnlyIP|192.168.56.11|--flags|RDONLYGUEST')) { throw 'IP property is incorrect.' }
function Get-DsfstVMInfo { @{ VMState = 'running'; nic2 = 'none' } }
$rejected = $false
try { Set-DsfstVMNetwork 'clone' 'test adapter' '192.168.56.11' } catch { $rejected = $true }
if (-not $rejected) { throw 'An active VM was reconfigured.' }
Write-Output 'VM network tests passed.'
