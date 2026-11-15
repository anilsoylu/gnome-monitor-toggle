# Headless test image: real Mutter with virtual monitors, no physical display.
FROM ubuntu:26.04

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      mutter dbus python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gettext desktop-file-utils xdg-user-dirs \
 && rm -rf /var/lib/apt/lists/*

RUN useradd -m tester
USER tester
ENV XDG_RUNTIME_DIR=/tmp/xdg-runtime
WORKDIR /src
