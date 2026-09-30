# Shared by browser setup and the clone factory. No guest credentials are stored.
function Invoke-DsfstVBox([string[]]$Arguments, [switch]$AllowFailure) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $raw = & $script:DsfstVBox @Arguments 2>&1; $code = $LASTEXITCODE }
    finally { $ErrorActionPreference = $previous }
    $lines = @($raw | ForEach-Object { $_.ToString() })
    if ($code -ne 0 -and -not $AllowFailure) { throw "VBoxManage failed ($code): $($lines -join ' ')" }
    [pscustomobject]@{ ExitCode = $code; Lines = $lines }
}
function Get-DsfstVMInfo([string]$Name) {
    $info = @{}
    foreach ($line in (Invoke-DsfstVBox @('showvminfo', $Name, '--machinereadable')).Lines) {
        if ($line -match '^([^=]+)=(.*)$') { $info[$Matches[1].Trim('"')] = $Matches[2].Trim('"') }
    }
    $info
}
function Get-DsfstExtra([string]$Name, [string]$Key) {
    foreach ($line in (Invoke-DsfstVBox @('getextradata', $Name, $Key)).Lines) {
        if ($line -match '^Value: (.*)$') { return $Matches[1] }
    }
    return $null
}
function Get-DsfstVMNames {
    foreach ($line in (Invoke-DsfstVBox @('list', 'vms')).Lines) {
        if ($line -match '^"(.+)" \{[0-9a-fA-F-]+\}$') { $Matches[1] }
    }
}
function Get-DsfstHostOnlyAdapter([switch]$Create) {
    $entries = ((Invoke-DsfstVBox @('list', 'hostonlyifs')).Lines -join "`n") -split "`n\s*`n"
    foreach ($entry in $entries) {
        if ($entry -match '(?m)^IPAddress:\s+192\.168\.56\.1\s*$' -and $entry -match '(?m)^NetworkMask:\s+255\.255\.255\.0\s*$') {
            if ($entry -match '(?m)^Name:\s+(.+)$') { return $Matches[1].Trim() }
        }
    }
    if (-not $Create) { throw 'No 192.168.56.1/24 VirtualBox host-only adapter exists.' }
    $conflicts = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -like '192.168.56.*' }
    if ($conflicts) { throw '192.168.56.0/24 is already used by another Windows adapter.' }
    $created = (Invoke-DsfstVBox @('hostonlyif', 'create')).Lines -join "`n"
    if ($created -notmatch "Interface '([^']+)' was successfully created") { throw "Cannot identify the new host-only adapter: $created" }
    $adapter = $Matches[1]
    Invoke-DsfstVBox @('hostonlyif', 'ipconfig', $adapter, '--ip=192.168.56.1', '--netmask=255.255.255.0') | Out-Null
    $adapter
}
function Get-DsfstAddress([string]$Name, [string]$Requested) {
    $used = @{}
    foreach ($other in (Get-DsfstVMNames)) {
        if ($other -ne $Name) {
            $address = Get-DsfstExtra $other 'dsfst/network-ip'
            if ($address) { $used[$address] = $other }
        }
    }
    $existing = Get-DsfstExtra $Name 'dsfst/network-ip'
    $candidate = if ($Requested) { $Requested } elseif ($existing) { $existing } else { $null }
    if ($candidate) {
        if ($candidate -notmatch '^192\.168\.56\.[1-9][0-9]$') { throw 'Use an address from 192.168.56.10 through 192.168.56.99.' }
        if ($used.ContainsKey($candidate)) {
            if ($Requested) { throw "$candidate belongs to $($used[$candidate])." }
            $candidate = $null # A clone can inherit its template's metadata.
        }
        if ($candidate -and $candidate -eq $existing) { return $candidate }
    }
    $ping = New-Object System.Net.NetworkInformation.Ping
    try {
        $candidates = if ($candidate) { @($candidate) } else { @(10..99 | ForEach-Object { "192.168.56.$_" }) }
        foreach ($address in $candidates) {
            if ($used.ContainsKey($address)) { continue }
            try { $reply = $ping.Send($address, 300) } catch { $reply = $null }
            if ($reply -and $reply.Status -eq 'Success') { continue }
            return $address
        }
    } finally { $ping.Dispose() }
    throw 'No unused host-only address is available.'
}
function Set-DsfstVMNetwork([string]$Name, [string]$Adapter, [string]$Address) {
    $info = Get-DsfstVMInfo $Name
    if ($info['VMState'] -ne 'poweroff') { throw "$Name must be fully shut down to attach its host-only adapter." }
    if ($info['nic2'] -notin @('none', 'hostonly')) { throw "$Name already uses adapter 2 for another network." }
    if ($info['nic2'] -eq 'hostonly' -and $info['hostonlyadapter2'] -and $info['hostonlyadapter2'] -ne $Adapter) {
        throw "$Name's adapter 2 belongs to a different host-only network."
    }
    # Poweroff can be reported a moment before VirtualBox releases its session lock.
    $deadline = (Get-Date).AddSeconds(30)
    do {
        $changed = Invoke-DsfstVBox @('modifyvm', $Name, '--nic2=hostonly', "--hostonlyadapter2=$Adapter", '--cableconnected2=on') -AllowFailure
        if ($changed.ExitCode -eq 0) { break }
        if (($changed.Lines -join ' ') -notmatch 'already locked|being unlocked' -or (Get-Date) -gt $deadline) {
            throw "Cannot attach host-only adapter: $($changed.Lines -join ' ')"
        }
        Start-Sleep -Seconds 1
    } while ($true)
    Set-DsfstVMProperties $Name $Address
}
function Set-DsfstVMProperties([string]$Name, [string]$Address) {
    $mac = (Get-DsfstVMInfo $Name)['macaddress2'].ToLowerInvariant()
    if ($mac -notmatch '^[0-9a-f]{12}$') { throw "Cannot determine $Name's adapter MAC address." }
    $colonMac = ($mac -split '(.{2})' | Where-Object { $_ }) -join ':'
    foreach ($pair in @(@('/DSFST/HostOnlyIP', $Address), @('/DSFST/HostIP', '192.168.56.1'), @('/DSFST/HostOnlyMAC', $colonMac))) {
        Invoke-DsfstVBox @('guestproperty', 'set', $Name, $pair[0], $pair[1], '--flags', 'RDONLYGUEST') | Out-Null
    }
    Invoke-DsfstVBox @('setextradata', $Name, 'dsfst/network-ip', $Address) | Out-Null
}
function Save-DsfstVMAddresses {
    $rows = @(foreach ($name in (Get-DsfstVMNames)) {
        $address = Get-DsfstExtra $name 'dsfst/network-ip'
        if ($address) {
            [pscustomobject]@{ VM = $name; IP = $address; Dashboard = "http://${address}:3000/#/"; APIs = "http://${address}:3000/api" }
        }
    })
    ConvertTo-Json -InputObject $rows -Depth 3 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'vm-addresses.json') -Encoding UTF8
    $rows | Format-Table -AutoSize | Out-Host
}
