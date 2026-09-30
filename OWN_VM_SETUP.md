# Run D.S.F.S.T on your own Ubuntu VM

This guide uses a Windows PC with **Oracle VirtualBox** and your own Ubuntu
installation. The Windows helpers use VirtualBox's `VBoxManage`; VMware
Workstation is a different product and cannot run these helpers.

## 1. Prepare your VM

- Install [Oracle VirtualBox for Windows](https://www.oracle.com/virtualization/technologies/vm/downloads/virtualbox-downloads.html)
  in its default location, `C:\Program Files\Oracle\VirtualBox`.
- Use an Ubuntu **x86-64/amd64** guest. Ubuntu 24.04 LTS is the version tested
  with this project; its images are available from [Ubuntu](https://releases.ubuntu.com/24.04/).
- As a starting allocation for this lab, give the guest **4 GB RAM** and a
  **40 GB virtual disk**. Allow extra host disk space for images, data and
  snapshots. The clone script allocates 4 GB RAM and one CPU per clone and
  checks host resources before creating or starting them.
- The CPU must expose **AVX** to Ubuntu. Use a normal Ubuntu account with
  `sudo` access, internet access, and a home directory without spaces.
- Leave **Adapter 1 = NAT** for internet access and **Adapter 2 disabled**.
  The browser helper configures Adapter 2 later. Use a dedicated test VM:
  experiments apply CPU, memory or network load to that VM.

If Ubuntu is already installed, keep it and follow the remaining steps.
Note the exact VM name shown in VirtualBox and your Ubuntu username (`whoami`).
Examples below use `My Ubuntu VM` and `myuser`; replace both with yours.

### Install Guest Additions

Guest Additions are needed for the Windows setup and database probe helpers.
In the Ubuntu terminal, install build prerequisites:

```bash
sudo apt update
sudo apt install -y build-essential dkms linux-headers-$(uname -r)
```

In the running VM window, choose **Devices > Insert Guest Additions CD image**.
Open the mounted CD in Ubuntu's Files app, open a terminal in that directory,
and run:

```bash
sudo sh ./VBoxLinuxAdditions.run
sudo reboot
```

After reboot, `VBoxControl --version` should print a version. Use the Guest
Additions supplied by your installed VirtualBox version. See
[Oracle's Guest Additions instructions](https://docs.oracle.com/en/virtualization/virtualbox/7.2/user/guestadditions.html)
if the CD does not mount or its kernel modules fail to build.

## 2. Get the same project branch in Ubuntu and Windows

**Inside Ubuntu**, clone the branch into your home directory:

```bash
sudo apt install -y git
git clone --branch main-based-dev-branch --single-branch https://github.com/TH-800/D.S.F.S.T.git "$HOME/D.S.F.S.T"
cd "$HOME/D.S.F.S.T"
```

**On Windows**, clone the same repository and select `main-based-dev-branch`
in GitHub Desktop. Alternatively, open the
[branch on GitHub](https://github.com/TH-800/D.S.F.S.T/tree/main-based-dev-branch),
choose **Code > Download ZIP**, and extract it. Git is not required on Windows
for the batch helpers. Keep each `.bat`, its `.ps1`, and the rest of the project
together in the extracted folder.

You can also extract that branch's ZIP into Ubuntu instead of using Git.
The guest project path must have no spaces and must remain at the installed
location. The repository contains source code; Ubuntu, database images,
dependencies and VM passwords are not bundled.

## 3. Install and enable startup inside Ubuntu

From the guest project folder, run these commands **as your normal user**:

```bash
bash install_dsfst.sh
bash enable_dsfst_autostart.sh
sudo systemctl start dsfst.service
```

Wait for each command to succeed before running the next. Do not prefix the
installer or autostart installer with `sudo`; they request it when needed.
The initial setup needs your Ubuntu administrator password.

The installer installs Python and frontend dependencies, Node.js, Docker
Compose, monitoring and injection tools; downloads MongoDB, InfluxDB and Redis
images; builds the dashboard; and generates local database credentials.
Autostart installs the services that launch the databases, APIs, dashboard and
metrics writer at boot. You do not need to launch `RunALL.py` separately.

Check the app inside Ubuntu:

```bash
systemctl status dsfst.service --no-pager
curl -fsS http://127.0.0.1:8009/state
```

Open `http://localhost:3000/#/` in the guest browser. Switch **Mock Data** to
**Live API** to display actual VM measurements.

For terminal use without autostart, run `bash start_dsfst.sh` after installation
and press Ctrl+C to stop it. Use either the service or this manual launcher at
a time; starting another launcher while one is active reports already running.

## 4. Enable Windows browser access once

Keep the VM running with the app started. Open **Windows Command Prompt** in
the Windows project folder and run:

```bat
enable_vm_browser.bat -VmName "My Ubuntu VM" -GuestUser myuser
```

The helper asks once for that Ubuntu user's password. It copies the browser
access files, rebuilds the dashboard, gracefully reboots if it needs to attach
Adapter 2, installs the network boot service, and checks the external API.
Finish or stop any experiment before running it. If service path detection
fails, specify the actual guest path:

```bat
enable_vm_browser.bat -VmName "My Ubuntu VM" -GuestUser myuser -GuestProjectPath "/home/myuser/D.S.F.S.T"
```

The script defaults to `LinuxVm1` and `rat` when those arguments are omitted;
on your own computer, provide your own VM name and username. In PowerShell,
prefix batch filenames with `.\`, for example `.\enable_vm_browser.bat`.

The helper assigns an unused address from `192.168.56.10` to `192.168.56.99`.
Windows uses `192.168.56.1`; the VM keeps NAT internet access. The address map
is saved in the Windows project folder as `vm-addresses.json`.

Use the **address printed by setup**, for example:

| Purpose | Windows browser URL |
| --- | --- |
| Dashboard | `http://192.168.56.10:3000/#/` |
| API directory | `http://192.168.56.10:3000/api` |
| Metrics and database result API | `http://192.168.56.10:3000/api/8008/docs` |
| Experiment control API | `http://192.168.56.10:3000/api/8009/docs` |

On later boots, start the VM in VirtualBox and wait for the app to become ready.
The network service restores its assigned IP, and `dsfst.service` starts the
app automatically. There is no Ubuntu password prompt for this boot process.
Normal login and manual `sudo` commands can still require your password.

The browser addresses work on this Windows host and its host-only network.
The app has no user login; keep access within your private lab. Python APIs
and database ports stay on guest loopback. The dashboard's gateway exposes
their API routes through TCP 3000 on the VM's assigned host-only address.

## 5. Read data from Windows and verify the installation

In **Windows PowerShell**, substitute your VM's URL:

```powershell
$base = 'http://192.168.56.10:3000'
Invoke-RestMethod "$base/api/8009/state"
Invoke-RestMethod "$base/api/8008/metrics/latest" | ConvertTo-Json -Depth 8
Invoke-RestMethod "$base/api/8008/experiments?limit=10" | ConvertTo-Json -Depth 8
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tests\live_vm_browser_smoke.ps1 -BaseUrl $base
```

The smoke script checks the dashboard, APIs, request validation and fresh
stored metrics. Add `-RunExperiment` only when you want its 15-second, 10% CPU
experiment; this creates a record and checks completion and its stored report.

The `/docs` pages let you send GET and POST requests from a browser. A Windows
collector can poll the JSON metrics and experiment APIs and insert the values
into another database. Include the VM name or IP with each collected record;
the project does not automatically copy data into your external database.
See [browser API examples](VM_BROWSER_README.md) for URLs and POST examples.

To inspect MongoDB, InfluxDB or Redis directly through Guest Control, use:

```bat
dsfst_vm_access.bat db -VmName "My Ubuntu VM" -GuestUser myuser
```

That helper requests the guest password. HTTP API access does not need Guest
Control credentials. See [database probes](DB_API_README.md) and
[Windows guest access](VM_ACCESS_README.md).

## 6. Stop, restart and diagnose the app

Run inside Ubuntu, from the project folder:

```bash
bash stop_dsfst.sh
sudo systemctl start dsfst.service
```

The stop script runs `sudo systemctl stop dsfst.service`. It stops the app;
database containers and their saved data remain. To restart an active service,
use `sudo systemctl restart dsfst.service` after stopping any experiment.

| Symptom | Check or action |
| --- | --- |
| Installer fails | Fix the reported dependency, network or AVX problem and rerun `bash install_dsfst.sh`; incomplete installs cannot start. |
| Windows setup cannot reach Guest Additions | Check VM name, guest username/password, `VBoxControl --version`, and that the VM is running rather than saved or paused. |
| Browser cannot connect after boot | Check `systemctl status dsfst-network.service dsfst.service --no-pager` and `journalctl -u dsfst-network.service -u dsfst.service -n 100 --no-pager`; use the assigned host-only IP. |
| Metrics missing immediately after startup | Allow the databases and writer to become ready, then repeat the metrics request and check the service journal. |
| Dashboard shows generated readings | Switch Mock Data to Live API. Missing live readings are shown as unavailable. |
| Already running | Use the existing service, or stop it before starting a manual launcher. |
| Port conflict | Free application ports 3000 and 8000-8010 inside the guest; database ports are allocated automatically. |
| Snapshot name already exists | Use a fresh `-SnapshotName` when preparing an updated template and the same name when cloning. |

Keep `.dsfst/`, both generated `.env` files, and Docker volumes private and
intact. Do not use `docker compose down -v` to restart: it deletes database
volumes. See [START_HERE.txt](START_HERE.txt) for preserving existing installs.

## 7. Optional: clone your prepared VM

After the single VM works, prepare a snapshot from Windows Command Prompt:

```bat
enable_vm_browser.bat -VmName "My Ubuntu VM" -GuestUser myuser -PrepareTemplate
create_dsfst_vms.bat 2 -TemplateVm "My Ubuntu VM" -DryRun
create_dsfst_vms.bat 2 -TemplateVm "My Ubuntu VM"
```

The default snapshot is `dsfst-browser-ready`. Preparation shuts the VM down
gracefully to take an offline snapshot and starts it again. The factory creates
full clones named `DSFST-User-001`, `DSFST-User-002`, and so on. The count is the
total set wanted, so repeated runs reuse existing managed VMs.

Each clone gets its own disk, MAC and permanent IP. On first boot it resets
only its copied D.S.F.S.T database volumes, generates fresh app credentials,
and starts the app. The source VM's records are preserved. Ubuntu accounts
and their login passwords are copied from the template; change a clone's login
password before handing it to someone else. Cloning and automatic startup
do not ask for the guest password.

After updating the template, prepare a new snapshot name and select it in
both commands. See [VM_FACTORY_README.txt](VM_FACTORY_README.txt) for details.
See [VALIDATION.txt](VALIDATION.txt) for the checks performed and their scope.
