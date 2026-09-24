D.S.F.S.T VirtualBox VM launcher (Windows)
===========================================

This launcher clones an Ubuntu VM that has already been prepared with this
project. On the original Windows host, that VM is LinuxVm1. It does not
download or reinstall Ubuntu for every user. Each clone has its own virtual
disk and NAT network adapter. On first boot, a root-owned guest service clears
only that clone's copied D.S.F.S.T database volumes, generates new application
database credentials, and starts the app. The source VM's data is kept.

Run this from a Windows Command Prompt in this folder:

    create_dsfst_vms.bat 1

Replace 1 with the number of VMs wanted. The script creates DSFST-User-001,
DSFST-User-002, and so on. Existing managed VMs are reused. It starts their
VirtualBox windows unless -NoStart is supplied. To preview its actions:

    create_dsfst_vms.bat 2 -DryRun

To clone a prepared VM with another name:

    create_dsfst_vms.bat 2 -TemplateVm "My Ubuntu VM"

The default snapshot name is dsfst-ready. If you chose another name, add
-SnapshotName "your snapshot name".

Each clone is assigned 4 GB RAM and one CPU. The launcher checks host memory
and disk space before creating VMs. The number that can run at once depends
on the host's available RAM and other running VMs.
The clone's dashboard is at http://localhost:3000/ inside that VM. Database
ports are accessible only on that VM's loopback interface.
Inside a VM, use `systemctl status dsfst.service` to check the app. From the
project folder, run `bash stop_dsfst.sh` to stop it and
`sudo systemctl start dsfst.service` to start it again. This stops the app
service; the database containers and their data remain available.

No guest password is required by the Windows launcher or by the app's boot
service. Logging into Ubuntu still uses the template account and its copied
password. Change that password before giving a clone to another person.

On another Windows computer, install Oracle VirtualBox and prepare one Ubuntu
x86-64 VM with a sudo-capable user, internet access, and AVX exposed to the VM.
Copy this entire project folder into that VM. In its project folder, run:

    bash install_dsfst.sh
    bash enable_dsfst_autostart.sh

The one-time setup asks for that Ubuntu user's sudo password. Check that
`sudo systemctl start dsfst.service` starts the app. Then shut down the VM
cleanly. From Windows Command Prompt, run these commands with your VM's name:

    "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" setextradata "My Ubuntu VM" dsfst/template-ready 1
    "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" snapshot "My Ubuntu VM" take dsfst-ready
    create_dsfst_vms.bat 2 -TemplateVm "My Ubuntu VM" -DryRun
    create_dsfst_vms.bat 2 -TemplateVm "My Ubuntu VM"

The prepared VM must be powered off before taking its snapshot. Keep the
project at the same path inside the guest after installing its boot service.
The launcher runs on Windows and uses the local VirtualBox installation; it
does not require the Ubuntu password when cloning or starting prepared VMs.
Users with an arbitrary Ubuntu VM still need to perform the one-time setup.

The files that set up the boot service are enable_dsfst_autostart.sh and
dsfst_clone_init.sh. If you later change the project in the source VM, its
existing snapshot will still contain the older version; create a new prepared
snapshot before cloning that version.
