{
  lib,
  python3Packages,
  wrapGAppsHook3,
  gobject-introspection,
  gtk3,
  glib,
  httrack,
  ffmpeg,
}:
let
  python = python3Packages.python;
  version = "unstable-2025-05-01";

  scripts = python3Packages.buildPythonPackage {
    pname = "downys-scripts";
    inherit version;
    pyproject = false;
    strictDeps = true;

    src = lib.fileset.toSource {
      root = ./.;
      fileset = ./scripts;
    };

    propagatedBuildInputs = [
      python3Packages.yt-dlp
    ];

    installPhase = ''
      runHook preInstall

      mkdir -p "$out/${python.sitePackages}"
      cp -r $src/scripts/ "$out/${python.sitePackages}/"

      runHook postInstall
    '';
  };
in
python3Packages.buildPythonApplication {
  pname = "downys";
  inherit version;
  pyproject = false;
  strictDeps = true;

  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./scripts
      ./main.py
    ];
  };

  nativeBuildInputs = [
    wrapGAppsHook3
    gobject-introspection
  ];

  buildInputs = [
    gtk3
    glib
  ];

  propagatedBuildInputs = [
    python3Packages.pygobject3
    scripts
    httrack
    ffmpeg
  ];

  installPhase = ''
    runHook preInstall

    install -D -m 755 $src/main.py "$out/bin/downys.py"

    runHook postInstall
  '';

  meta = {
    description = "";
    homepage = "https://github.com/kovachUa/downys";
    # license = lib.licenses.unfree; # TODO: update license
    maintainers = [ ];
    mainProgram = "downys";
    platforms = python.meta.platforms;
  };
}
