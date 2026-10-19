# WolfLink local 0.3.0b1 – Hinweise für die Testrunde

Stand: 19. Oktober 2026. Dieses feste Betapaket ist für freiwillige Tests bestimmt.

## Was im ZIP liegt

- `custom_components/wolflink_local/`: vollständige Integration einschließlich Oberfläche, Grafiken und Dokumentation.
- `INSTALLATION.md`: Installation, Update und Fehlerhilfe.
- `BESCHREIBUNG.md`: Funktionsumfang und bekannte Grenzen.
- `CHANGELOG.md`: Versionsänderungen.
- `TESTHINWEISE.md`: diese Checkliste.

Nur den Integrationsordner nach `/config/custom_components/` kopieren. Die Dokumente liegen zur Weitergabe zusätzlich direkt im ZIP. Kein `www`-Ordner und kein separates Dashboard erforderlich. SHA-256-Prüfsumme separat mitliefern.

## Vorbereitung

1. Für das ISM7 möglichst eine DHCP-Reservierung im Router einrichten. Home Assistant sichern. Modell und Firmware der Anlage sowie die HA-Version notieren.
2. WOLF-App/Smartset und andere lokale ISM7-Clients vollständig schließen. Das Modul erlaubt nur eine lokale Verbindung.
3. Nach INSTALLATION.md installieren, eigene Modul-IP und eigenes Modulpasswort verwenden.
4. Neue Einträge zunächst im voreingestellten Read-only-Modus belassen. Standardabfragetakt: 60 Sekunden.

## Bitte prüfen

- Integration erscheint nach Neustart; automatische WolfLink-Seite öffnet sich.
- Messwerte und Betriebszustände mit dem Bedienmodul vergleichen, insbesondere Vorlauf, Rücklauf und Warmwasser.
- Bedienung, Übersicht, Heizung, Warmwasser und verfügbare Energiestatistik auf Desktop und Mobilgerät öffnen.
- Geräteinformationen erscheinen passend zur Ausstattung. Fehlende Werte dürfen nicht als erfundene Nullwerte erscheinen.
- Mit installiertem Raumfühler: Raumtemperatur in Bedienung, Übersicht und Heizung vergleichen. Ohne Fühler bleibt sie ausgeblendet.
- Nach HA-Neustart und normalem Verbindungsabbruch werden Werte wieder aktualisiert.
- Schreibtests nur bewusst nach Freigabe in den Integrationsoptionen und nur im Rahmen der eigenen Anlage durchführen. Ausgangswert notieren, Bestätigung abwarten und gewünschten Zustand wiederherstellen. Keine unnötigen Schaltbefehle zum Testen.

## Rückmeldung

Bitte Paketversion 0.3.0b1, HA-Version, Heizungsmodell, BM-2-/ISM7-Firmware, Browser/Gerät, erwartetes und tatsächliches Verhalten sowie reproduzierbare Schritte nennen. Auch eine erfolgreiche Neuinstallation ist eine wichtige Rückmeldung.

Keine Modulpasswörter, Token, Seriennummern, vollständigen HA-Konfigurationen oder unbereinigten Diagnosen weitergeben. Screenshots auf Namen, IP-Adressen und andere persönliche Angaben prüfen. Der gemeinsame Protokollschlüssel im Lieferumfang ist eine erforderliche öffentliche Protokollressource und kein persönlicher Modulzugang.

## Grenzen und Rückkehr

Andere Modelle und optionale Sensoren sind noch nicht durchgängig praktisch geprüft. Tages-/Jahresenergiewerte sind rechnerische Anlagenwerte. Zeitfensterende 24:00 wird nicht unterstützt. Weitere Grenzen stehen in BESCHREIBUNG.md.

Bei unerwartetem Verhalten Schreibzugriff deaktivieren oder den Integrationseintrag deaktivieren. Für eine Rückkehr den gesicherten Integrationsordner wiederherstellen und HA neu starten. Beim Wechsel von alten Domains ist eine neue Einrichtung nötig; den Ordner nicht nur umbenennen.
