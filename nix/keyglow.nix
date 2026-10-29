# Import from your NixOS configuration, e.g. imports = [ /home/nakul/projects/keyglow/nix/keyglow.nix ];
{ ... }:
{
  # Let the logged-in user (and the input group) open the keyboard's hidraw nodes without sudo.
  services.udev.extraRules = ''
    KERNEL=="hidraw*", ATTRS{idVendor}=="19f5", ATTRS{idProduct}=="3302", MODE="0660", GROUP="input", TAG+="uaccess"
  '';

  systemd.user.services.keyglow = {
    description = "Push Hyprland binds to the keyboard RGB";
    partOf = [ "graphical-session.target" ];
    after = [ "graphical-session.target" ];
    wantedBy = [ "graphical-session.target" ];
    path = [ "/etc/profiles/per-user/nakul" ]; # hyprctl, python3
    serviceConfig = {
      ExecStart = "/home/nakul/projects/keyglow/host/keyglow.py daemon";
      Restart = "on-failure";
      RestartSec = 3;
    };
  };
}
