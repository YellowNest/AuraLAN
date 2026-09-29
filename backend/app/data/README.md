# Offline vendor data

AuraLAN does not ship a household-specific or hand-picked MAC vendor table.

Vendor lookup is local and optional. At runtime AuraLAN reads common Linux OUI registry locations when present:

- `/usr/share/ieee-data/oui.txt`
- `/var/lib/ieee-data/oui.txt`
- `/usr/share/misc/oui.txt`
- `/usr/share/nmap/nmap-mac-prefixes`
- `/usr/share/arp-scan/ieee-oui.txt`

A custom offline registry can be supplied with `AURALAN_OUI_FILE`.

No MAC address is sent to an external lookup service. If no local registry contains a prefix, the vendor remains unknown.

An OUI identifies an organization, not a hardware model or owner. AuraLAN must never use it as proof of an exact device model.
