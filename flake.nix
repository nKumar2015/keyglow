{
  description = "keyglow: light up Hyprland Super binds on a QMK keyboard";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  };

  outputs = {
    self,
    nixpkgs,
    ...
  }: let
    systems = [
      "x86_64-linux"
      "aarch64-linux"
    ];

    forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

    # The host tool is a single stdlib-only script. hyprctl is deliberately not
    # bundled: it has to match the running Hyprland, so it comes from the user's PATH.
    mkKeyglow = pkgs:
      pkgs.stdenvNoCC.mkDerivation {
        pname = "keyglow";
        version = "0.1.0";
        src = ./host;

        # fixupPhase rewrites the `#!/usr/bin/env python3` shebang to this python.
        buildInputs = [pkgs.python3];

        installPhase = ''
          runHook preInstall
          install -Dm755 keyglow.py $out/bin/keyglow
          runHook postInstall
        '';

        meta = {
          description = "Light up Hyprland Super binds on a QMK keyboard";
          homepage = "https://github.com/nKumar2015/keyglow";
          mainProgram = "keyglow";
          platforms = pkgs.lib.platforms.linux;
        };
      };
  in {
    packages = forAllSystems (pkgs: {
      keyglow = mkKeyglow pkgs;
      default = self.packages.${pkgs.stdenv.hostPlatform.system}.keyglow;
    });

    overlays.default = final: _prev: {keyglow = mkKeyglow final;};

    # System side: a udev rule so the logged-in user can open the keyboard's raw HID node.
    nixosModules.default = {
      config,
      lib,
      ...
    }: let
      cfg = config.hardware.keyglow;
    in {
      options.hardware.keyglow = {
        enable = lib.mkEnableOption "non-root access to the raw HID interface of keyboards running keyglow firmware";

        devices = lib.mkOption {
          type = with lib.types; listOf (strMatching "[0-9a-f]{4}:[0-9a-f]{4}");
          default = ["19f5:3302"]; # NuPhy Halo96 V2
          example = ["19f5:3302" "feed:6060"];
          description = "USB `vendor:product` IDs (lowercase hex) of the keyboards.";
        };
      };

      config = lib.mkIf cfg.enable {
        services.udev.extraRules =
          lib.concatMapStrings (id: let
            vid = builtins.head (lib.splitString ":" id);
            pid = lib.last (lib.splitString ":" id);
          in ''
            KERNEL=="hidraw*", ATTRS{idVendor}=="${vid}", ATTRS{idProduct}=="${pid}", MODE="0660", GROUP="input", TAG+="uaccess"
          '')
          cfg.devices;
      };
    };

    # User side: the daemon and its config.
    homeManagerModules.default = {
      config,
      lib,
      pkgs,
      ...
    }: let
      cfg = config.services.keyglow;
      toml = pkgs.formats.toml {};
      color = lib.types.strMatching "#[0-9a-fA-F]{6}";
      configFile = toml.generate "keyglow.toml" (lib.recursiveUpdate {
          colors.default = cfg.highlightColor;
          filter.exclude_keys = cfg.ignore;
        }
        cfg.settings);
    in {
      options.services.keyglow = {
        enable = lib.mkEnableOption "keyglow, which keeps the keyboard's glow table in sync with Hyprland's binds";

        package = lib.mkOption {
          type = lib.types.package;
          default = mkKeyglow pkgs;
          defaultText = lib.literalExpression "keyglow.packages.\${system}.default";
          description = "The keyglow package.";
        };

        highlightColor = lib.mkOption {
          type = color;
          default = "#00b4ff";
          example = "#ffffff";
          description = ''
            Color of every key that has a bind while Super is held.
            Per-dispatcher or per-combo colors in {option}`settings.colors` take precedence.
          '';
        };

        ignore = lib.mkOption {
          type = with lib.types; listOf str;
          default = [];
          example = ["SUPER+Q" "SUPER+SHIFT+M" "SUPER+KP_*" "SUPER+?"];
          description = ''
            Binds to leave dark, as `MODS+KEY` combos in any modifier order and case
            (`keyglow show` lists the names). Shell-style globs (`*`, `?`) are allowed.
          '';
        };

        settings = lib.mkOption {
          inherit (toml) type;
          default = {};
          example = lib.literalExpression ''
            {
              colors.dispatcher = { exec_cmd = "#00ff80"; close = "#ff2020"; };
              filter.exclude_dispatchers = [ "focus" "move" ];
            }
          '';
          description = ''
            Anything else for {file}`$XDG_CONFIG_HOME/keyglow/config.toml` (see config.example.toml),
            merged over {option}`highlightColor` and {option}`ignore`.
          '';
        };

        target = lib.mkOption {
          type = lib.types.str;
          default = "graphical-session.target";
          example = "hyprland-session.target";
          description = "systemd user target the daemon starts with and stops with.";
        };
      };

      config = lib.mkIf cfg.enable {
        home.packages = [cfg.package];

        xdg.configFile."keyglow/config.toml".source = configFile;

        systemd.user.services.keyglow = {
          Unit = {
            Description = "keyglow: push Hyprland binds to the keyboard";
            PartOf = [cfg.target];
            After = [cfg.target];
            X-Restart-Triggers = ["${configFile}"];
          };
          Service = {
            ExecStart = "${lib.getExe cfg.package} daemon";
            Restart = "on-failure";
            RestartSec = 3;
            # hyprctl has to match the running Hyprland, so take it from the user's
            # and the system's profile instead of pinning one here.
            Environment = ["PATH=${config.home.profileDirectory}/bin:/run/current-system/sw/bin"];
          };
          Install.WantedBy = [cfg.target];
        };
      };
    };

    # Firmware build and flash tools; see README.
    devShells = forAllSystems (pkgs: {
      default = pkgs.mkShell {
        packages = with pkgs; [qmk dfu-util python3];
      };
    });

    formatter = forAllSystems (pkgs: pkgs.alejandra);
  };
}
