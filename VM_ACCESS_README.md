# Read D.S.F.S.T from Windows while its VirtualBox VM is running

Run `dsfst_vm_access.bat` from Windows Command Prompt in this project folder.
It uses VirtualBox Guest Additions to execute `dsfst_probe.py` inside the VM
and prints the JSON reply on Windows. API GET/POST requests and database reads
therefore use the VM's existing loopback addresses. No database or API port
needs to be exposed on the Windows host or on the network.

Requirements:

- Oracle VirtualBox and Guest Additions installed in the Ubuntu VM.
- The VM is running and D.S.F.S.T has been installed (`.venv` and `.env` exist).
- The app service is active, or `bash start_dsfst.sh` is running, for API calls.
- The Ubuntu account can log in through VirtualBox Guest Control. The script
  can write to the project folder. The script prompts for its password and
  removes the temporary password file afterward.

Examples for the prepared `LinuxVm1` with its `rat` account:

```bat
dsfst_vm_access.bat -Action status
dsfst_vm_access.bat -Action db
dsfst_vm_access.bat -Action mongo -Collection experiments -Limit 10
dsfst_vm_access.bat -Action mongo -Collection logs -Limit 10
dsfst_vm_access.bat -Action influx -Minutes 60 -Limit 20
dsfst_vm_access.bat -Action redis
dsfst_vm_access.bat -Action api -Method GET -Port 8009 -ApiPath /state
dsfst_vm_access.bat -Action api -Method GET -Port 8008 -ApiPath "/experiments?limit=5"
```

For another VM, add `-VmName "My Ubuntu VM" -GuestUser myuser`. The script
reads the project path from `dsfst.service`; if that service is not installed,
also supply `-GuestProjectPath "/home/myuser/path/to/project"`.

To send a JSON body, save it to a file on Windows and use POST. For example:

```bat
dsfst_vm_access.bat -Action api -Method POST -Port 8009 -ApiPath /experiments -JsonFile request.json
```

The file is copied to a temporary path in the VM and removed after the API
request. A POST to `/experiments` creates a record; `/experiments/<id>/start`
starts a real fault injection, so use that route deliberately. `-PasswordFile`
can point to a protected file containing the Ubuntu password for automation.
No password is stored in the project folder.

`db` returns collection counts, latest metrics, and state. `mongo`, `influx`,
and `redis` return bounded database contents. See `DB_API_README.md` for the
guest-side probe and API details.
