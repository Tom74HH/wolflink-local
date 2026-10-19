# WolfLink local installieren

## Voraussetzungen

- Home Assistant 2026.10.1 als geprüfter Entwicklungsstand.
- Für Lokal: unterstütztes ISM7 im eigenen Netzwerk, Modul-IP und Modulpasswort. Lokal geprüft: CGB-2/CGW-2 mit einem BM-2. Andere Anlagen sind nicht vollständig geprüft.

## Neuinstallation

1. ZIP entpacken.
2. Den enthaltenen Ordner `custom_components/wolflink_local` in die HA-Konfiguration kopieren. Falls `custom_components` noch fehlt, diesen Ordner anlegen.
3. Prüfen: Die Datei liegt unter `/config/custom_components/wolflink_local/manifest.json`. Keine zusätzliche Unterordnerebene anlegen.
4. Home Assistant neu starten.
5. Einstellungen → Geräte & Dienste → Integration hinzufügen → **WolfLink local**.
6. Modul-IP und eigenes Modulpasswort eingeben und das angezeigte Zertifikat bestätigen.
7. Die automatisch angelegte Seite **WolfLink local** in der Seitenleiste öffnen.

Kein zusätzliches Kopieren nach `www`, kein HACS und kein manuelles Dashboard erforderlich. Die persönliche Zuhause-Dashboardgestaltung des Entwicklers ist nicht Bestandteil des Pakets.

## Schreibzugriff freigeben

Neue Einträge sind zunächst Read-only. Werte mit der Anlage vergleichen. Zum Freigeben: Einstellungen → Geräte & Dienste → WolfLink local → beim gewünschten Eintrag **Konfigurieren** → Read-only deaktivieren. Eine Änderung durchführen und die Statusrückmeldung abwarten.

## Besonderheiten der lokalen Verbindung



## Update

1. Bisherigen Integrationsordner sichern.
2. Den Ordner `wolflink_local` durch die vollständige neue Version ersetzen.
3. HA neu starten und die Browserseite mit Strg+F5 oder Strg+Umschalt+R vollständig neu laden. Bei RDP vom Mac: Control+Shift+R.

Nicht die persönliche HA-Konfiguration oder `.storage` ersetzen. Bestehende Einträge und Zugangsdaten bleiben dort gespeichert. Bei alten manuellen Installationen nur veraltete WolfLink-JavaScript-Ressourcen unter `/local/` entfernen; andere Ressourcen beibehalten.

## Wenn etwas fehlt

- Integration nicht gefunden: Pfad kontrollieren, HA neu starten, Browser neu laden und HA-Protokoll prüfen.
- Lokal belegt: lokal verbundene App/Smartset schließen; keine parallelen Diagnoseprogramme verbinden.
- Fehlende Sensoren: Verfügbarkeit hängt von Modell, Firmware und Ausstattung ab. Ein nicht vorhandener Raumfühler erhält keinen Ersatzwert.
- Eine frische Installation auf einer anderen Hardware wurde nicht vollständig praktisch geprüft. Bekannte Grenzen stehen in README.md und BESCHREIBUNG.md.

## Weitergeben

Nur dieses Paket beziehungsweise den Integrationsordner weitergeben. Keine HA-Konfigurationsdateien, Diagnosen, Zugangsdaten oder persönlichen Dashboards hinzufügen. Gemeinsame Protokollzertifikate unter `local/` gehören zum erforderlichen Lieferumfang und sind keine persönlichen Zugangsdaten.

## Lokale Wiederverbindung

Nach Verbindungsabbruch meldet sich die Integration mit dem gespeicherten Modulpasswort erneut an. Belegt-, Pending- und allgemeine Modulfehler werden als vorübergehende Verbindungsfehler erneut versucht. Nur eine ausdrückliche Ablehnung der Zugangsdaten erfordert die Passwortkorrektur. Die bestehende lokale Read-only-/Schreibfreigabe bleibt auch bei erneuter Anmeldung erhalten. Verlorene Schreibbefehle werden nicht automatisch wiederholt.

Bei der Einrichtung Modul-IP und eigenes Modulpasswort eingeben. Die Verbindung erfolgt ausschließlich lokal über ISM7. Ordner und Integrationsdomain heißen `wolflink_local`. Dieses Paket richtet eine eigenständige lokale Integration ein.

Abfragetakt: 15–900 Sekunden, Standard 60 Sekunden. Das Modul erlaubt nur eine lokale Verbindung; lokal verbundene Apps und Smartset vorher schließen.

## Wechsel von älteren Paketen

Diese Version verwendet eine neue Integrationsdomain. Beim Wechsel von einem früheren Paket mit anderem Ordnernamen muss die lokale Integration neu eingerichtet werden; bloßes Umbenennen des alten Ordners genügt nicht. Vorher die alte Integration und deren Ordner sichern und die alte Verbindung beenden. Danach die neue lokale Integration einrichten. Eigene Dashboard-Verweise bei Bedarf neu zuordnen.
