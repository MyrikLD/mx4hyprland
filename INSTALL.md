# Setup udev rules

Copy udev rules file

```sh
sudo cp 99-logitech-mx_master_4.rules /etc/udev/rules.d/99-logitech-mx_master_4.rules
```

Reload udev rules

```sh
sudo udevadm control --reload-rule
sudo udevadm trigger
```

Add user to group input

```sh
sudo usermod -a -G input $USER
```


# Hyprland integration

Clone the repository

```sh
mkdir ~/.config/hypr/scripts
cd ~/.config/hypr/scripts
git clone https://github.com/MyrikLD/mx4hyprland.git
chmod 700 $HOME/.config/hypr/scripts/mx4hyprland/start.sh
```


Add `start.sh` script to hyprland configuration

    ~/.config/hypr/hyprland.conf
```
# Autostart for MX Master 4 haptic feedback
exec-once = $HOME/.config/hypr/scripts/mx4hyprland/start.sh
```

Log out and log in

